#!/usr/bin/env python3
"""Instrument lk2nd so we can see where it dies on the ReadBoy G35S.

The device has no UART and lk2nd stops fastboot before jumping to the kernel,
so the only way to observe the last stages of `boot_linux()` is to have lk2nd
write progress markers into RAM and read them back after the watchdog resets
the board.

Markers are written to 0x9FF80000 (the 512 KiB tail of lk2nd's scratch area,
unused unless ramoops is enabled) and read from a host with
`fastboot oem debug readl <addr>`.

Layout (32-bit words, little endian):
  0x9FF80000  stage marker      (see M_* below)
  0x9FF80004  is_scm_armv8_support()
  0x9FF80008  scm_call2() return value
  0x9FF8000C  scm_call() (legacy) return value
  0x9FF80010  update_device_tree() started
  0x9FF80014  update_device_tree() return value
  0x9FF80018  scm_elexec_call() entered
  0x9FF8001C  kernel entry argument
  0x9FF80020  dtb (tags) argument

Additionally the patched scm_elexec_call() no longer gives up after the first
convention fails: it retries with the legacy command-buffer call. On a board
whose firmware never had to switch 32->64 bit before, only one of the two may
be implemented, and trying both costs nothing because a successful call never
returns.
"""
import pathlib
import re
import sys

MARK_BASE = 0x9FF80000

SCM_HEAD = """\
static inline void lk2nd_dbg_write(unsigned idx, unsigned val)
{
	*(volatile unsigned *)(__MARK_BASE__u + 4u * idx) = val;
}

void scm_elexec_call(paddr_t kernel_entry, paddr_t dtb_offset)
{
	uint32_t svc_id = SCM_SVC_MILESTONE_32_64_ID;
	uint32_t cmd_id = SCM_SVC_MILESTONE_CMD_ID;
	void *cmd_buf;
	size_t cmd_len;
	static el1_system_param param __attribute__((aligned(0x1000)));
	scmcall_arg scm_arg = {0};
	uint32_t r_armv8 = 0xDEADBEEF;
	uint32_t r_legacy = 0xDEADBEEF;
	int armv8;

	param.el1_x0 = dtb_offset;
	param.el1_elr = kernel_entry;

	lk2nd_dbg_write(6, 0xB0070001);
	lk2nd_dbg_write(7, (unsigned)kernel_entry);
	lk2nd_dbg_write(8, (unsigned)dtb_offset);

	armv8 = is_scm_armv8_support() ? 1 : 0;
	lk2nd_dbg_write(1, (unsigned)armv8);

	dprintf(INFO, "Jumping to kernel via monitor (armv8=%d)\\n", armv8);

	cmd_buf = (void *)&param;
	cmd_len = sizeof(el1_system_param);

	if (armv8)
	{
		/* ARMv8 SCM convention first */
		scm_arg.x0 = MAKE_SIP_SCM_CMD(SCM_SVC_MILESTONE_32_64_ID,
					      SCM_SVC_MILESTONE_CMD_ID);
		scm_arg.x1 = MAKE_SCM_ARGS(0x2, SMC_PARAM_TYPE_BUFFER_READ);
		scm_arg.x2 = (uint32_t)&param;
		scm_arg.x3 = sizeof(el1_system_param);

		lk2nd_dbg_write(0, 0xB0070002);
		r_armv8 = scm_call2(&scm_arg, NULL);
		lk2nd_dbg_write(2, r_armv8);
	}
	else
	{
		lk2nd_dbg_write(0, 0xB0070003);
		r_legacy = scm_call(svc_id, cmd_id, cmd_buf, cmd_len, NULL, 0);
		lk2nd_dbg_write(3, r_legacy);
	}

	/* First convention failed (we only get here if it returned). Retry with
	 * the other one before giving up. */
	if (armv8)
	{
		lk2nd_dbg_write(0, 0xB0070004);
		r_legacy = scm_call(svc_id, cmd_id, cmd_buf, cmd_len, NULL, 0);
		lk2nd_dbg_write(3, r_legacy);
	}
	else
	{
		scm_arg.x0 = MAKE_SIP_SCM_CMD(SCM_SVC_MILESTONE_32_64_ID,
					      SCM_SVC_MILESTONE_CMD_ID);
		scm_arg.x1 = MAKE_SCM_ARGS(0x2, SMC_PARAM_TYPE_BUFFER_READ);
		scm_arg.x2 = (uint32_t)&param;
		scm_arg.x3 = sizeof(el1_system_param);

		lk2nd_dbg_write(0, 0xB0070005);
		r_armv8 = scm_call2(&scm_arg, NULL);
		lk2nd_dbg_write(2, r_armv8);
	}

	/* Both conventions returned: the firmware refused to switch to AArch64. */
	lk2nd_dbg_write(0, 0xB0070BAD);
	dprintf(CRITICAL, "Failed to jump to kernel\\n");
	ASSERT(0);
}
"""


def replace_function(src: str, signature: str, new_body: str) -> str:
    """Replace an entire top-level function, keeping anything after it."""
    start = src.index(signature)
    # walk backwards over a preceding comment block/blank lines is not needed:
    # callers pass the exact signature line.
    brace = src.index("{", start)
    depth = 0
    i = brace
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    end = i + 1
    return src[:start] + new_body.rstrip() + src[end:]


def patch_scm_c(path: pathlib.Path) -> None:
    src = path.read_text()
    sig = "void scm_elexec_call(paddr_t kernel_entry, paddr_t dtb_offset)"
    if sig not in src:
        raise SystemExit("scm_elexec_call signature not found in %s" % path)
    out = replace_function(src, sig, SCM_HEAD.replace("__MARK_BASE__", "0x%08X" % MARK_BASE))
    path.write_text(out)
    print("patched %s (scm_elexec_call instrumented + legacy fallback)" % path)


def patch_aboot_c(path: pathlib.Path) -> None:
    src = path.read_text()

    old_call = (
        "\tret = update_device_tree((void *)tags,(const char *)final_cmdline,\n"
        "\t\t\t\t boot_type, ramdisk, ramdisk_size);\n"
    )
    if old_call not in src:
        raise SystemExit("update_device_tree call not found in %s" % path)

    new_call = (
        "\t*(volatile unsigned *)0x%08Xu = 0xB0070010u;\n" % (MARK_BASE + 0x10)
        + old_call
        + "\t*(volatile unsigned *)0x%08Xu = (unsigned)ret;\n" % (MARK_BASE + 0x14)
    )
    src = src.replace(old_call, new_call, 1)

    path.write_text(src)
    print("patched %s (update_device_tree markers)" % path)


def main() -> None:
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("lk2nd")
    patch_scm_c(root / "platform/msm_shared/scm.c")
    patch_aboot_c(root / "app/aboot/aboot.c")


if __name__ == "__main__":
    main()
