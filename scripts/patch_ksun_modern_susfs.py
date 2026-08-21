#!/usr/bin/env python3
"""Add the minimal SUSFS glue to the pinned plain KernelSU Next v3.1.0 tree."""

from pathlib import Path
import sys


def replace(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"unexpected {label} replacement count in {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")


if len(sys.argv) != 2:
    raise SystemExit(f"usage: {Path(sys.argv[0]).name} <KernelSU-Next/kernel>")

root = Path(sys.argv[1])
required = ("Kconfig", "ksu.c", "setuid_hook.c", "supercalls.c", "selinux/selinux.c")
if not all((root / name).is_file() for name in required):
    raise SystemExit(f"not a KernelSU Next kernel directory: {root}")

susfs_kconfig = r'''

menu "KernelSU - SUSFS"

config KSU_SUSFS
	bool "KernelSU addon - SUSFS"
	depends on KSU
	depends on THREAD_INFO_IN_TASK
	default y
	help
	  Patch and enable SUSFS with KernelSU.

config KSU_SUSFS_SUS_PATH
	bool "Enable suspicious path hiding"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_SUS_MOUNT
	bool "Enable suspicious mount hiding"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_SUS_KSTAT
	bool "Enable suspicious kstat spoofing"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_TRY_UMOUNT
	bool "Enable KernelSU try_umount integration"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_SPOOF_UNAME
	bool "Enable uname spoofing"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_ENABLE_LOG
	bool "Enable SUSFS kernel logging"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS
	bool "Hide KernelSU and SUSFS symbols from kallsyms"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
	bool "Enable cmdline or bootconfig spoofing"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_OPEN_REDIRECT
	bool "Enable path open redirection"
	depends on KSU_SUSFS
	default y

config KSU_SUSFS_SUS_MAP
	bool "Enable suspicious map hiding"
	depends on KSU_SUSFS
	default y

endmenu
'''
replace(
    root / "Kconfig",
    "\nendmenu\n",
    susfs_kconfig + "\nendmenu\n",
    "SUSFS Kconfig menu",
)

replace(
    root / "ksu.c",
    '#include "file_wrapper.h"\n',
    '#include "file_wrapper.h"\n'
    "#ifdef CONFIG_KSU_SUSFS\n"
    "#include <linux/susfs.h>\n"
    "#endif\n",
    "ksu.c SUSFS include",
)
replace(
    root / "ksu.c",
    "\tksu_throne_tracker_init();\n\n\tksu_ksud_init();",
    "\tksu_throne_tracker_init();\n\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "\tsusfs_init();\n"
    "#endif\n\n"
    "\tksu_ksud_init();",
    "ksu.c SUSFS initialization",
)

replace(
    root / "setuid_hook.c",
    '#include "kernel_umount.h"\n',
    '#include "kernel_umount.h"\n'
    "#ifdef CONFIG_KSU_SUSFS\n"
    "#include <linux/susfs_def.h>\n"
    "\n"
    "static inline bool is_zygote_isolated_service_uid(uid_t uid)\n"
    "{\n"
    "\tuid %= 100000;\n"
    "\treturn uid >= 99000 && uid < 100000;\n"
    "}\n"
    "\n"
    "static inline bool is_zygote_normal_app_uid(uid_t uid)\n"
    "{\n"
    "\tuid %= 100000;\n"
    "\treturn uid >= 10000 && uid < 19999;\n"
    "}\n"
    "\n"
    "#ifdef CONFIG_KSU_SUSFS_SUS_PATH\n"
    "extern void susfs_run_sus_path_loop(void);\n"
    "#endif\n"
    "#endif\n",
    "setuid_hook.c SUSFS declarations",
)
replace(
    root / "setuid_hook.c",
    "    uid_t old_uid = current_uid().val;\n\n"
    '    pr_info("handle_setresuid from %d to %d\\n", old_uid, new_uid);',
    "    uid_t old_uid = current_uid().val;\n\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "    if (!is_zygote(current_cred()))\n"
    "        return 0;\n\n"
    "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n"
    "    if (is_zygote_isolated_service_uid(new_uid))\n"
    "        goto do_umount;\n"
    "#endif\n"
    "#endif\n\n"
    '    pr_info("handle_setresuid from %d to %d\\n", old_uid, new_uid);',
    "setuid_hook.c zygote gate",
)
replace(
    root / "setuid_hook.c",
    "    if (ksu_is_allow_uid_for_current(new_uid)) {",
    "#ifdef CONFIG_KSU_SUSFS\n"
    "    if (likely(is_zygote_normal_app_uid(new_uid) &&\n"
    "               ksu_uid_should_umount(new_uid)))\n"
    "        goto do_umount;\n"
    "#endif\n\n"
    "    if (ksu_is_allow_uid_for_current(new_uid)) {",
    "setuid_hook.c app umount gate",
)
replace(
    root / "setuid_hook.c",
    "    // Handle kernel umount\n"
    "    ksu_handle_umount(old_uid, new_uid);\n\n"
    "    return 0;\n",
    "#ifndef CONFIG_KSU_SUSFS\n"
    "    ksu_handle_umount(old_uid, new_uid);\n"
    "#endif\n\n"
    "    return 0;\n\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "do_umount:\n"
    "    ksu_handle_umount(old_uid, new_uid);\n"
    "#ifdef CONFIG_KSU_SUSFS_SUS_PATH\n"
    "    susfs_run_sus_path_loop();\n"
    "#endif\n"
    "    susfs_set_current_proc_umounted();\n"
    "    return 0;\n"
    "#endif\n",
    "setuid_hook.c SUSFS umount path",
)

replace(
    root / "supercalls.c",
    "#include <linux/utsname.h> // utsname() and uts_sem\n",
    "#include <linux/utsname.h> // utsname() and uts_sem\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "#include <linux/susfs.h>\n"
    "#endif\n",
    "supercalls.c SUSFS include",
)
replace(
    root / "supercalls.c",
    '#include "tiny_sulog.c"\n',
    '#include "tiny_sulog.c"\n\n'
    "#ifdef CONFIG_KSU_SUSFS\n"
    "bool susfs_is_boot_completed_triggered __read_mostly;\n"
    "#endif\n",
    "supercalls.c boot state",
)
replace(
    root / "supercalls.c",
    "\t\t\ton_boot_completed();\n",
    "\t\t\ton_boot_completed();\n"
    "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n"
    "\t\t\tsusfs_is_boot_completed_triggered = true;\n"
    "#endif\n",
    "supercalls.c boot completion",
)

dispatcher = r'''
#ifdef CONFIG_KSU_SUSFS
	if (magic1 == KSU_INSTALL_MAGIC1 && magic2 == SUSFS_MAGIC &&
	    current_uid().val == 0) {
		void __user **user_arg = (void __user **)&arg4;

#ifdef CONFIG_KSU_SUSFS_SUS_PATH
		if (cmd == CMD_SUSFS_ADD_SUS_PATH)
			susfs_add_sus_path(user_arg);
		else if (cmd == CMD_SUSFS_ADD_SUS_PATH_LOOP)
			susfs_add_sus_path_loop(user_arg);
		else
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
		if (cmd == CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS)
			susfs_set_hide_sus_mnts_for_non_su_procs(user_arg);
		else
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
		if (cmd == CMD_SUSFS_ADD_SUS_KSTAT ||
		    cmd == CMD_SUSFS_ADD_SUS_KSTAT_STATICALLY)
			susfs_add_sus_kstat(user_arg);
		else if (cmd == CMD_SUSFS_UPDATE_SUS_KSTAT)
			susfs_update_sus_kstat(user_arg);
		else
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
		if (cmd == CMD_SUSFS_SET_UNAME)
			susfs_set_uname(user_arg);
		else
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
		if (cmd == CMD_SUSFS_ENABLE_LOG)
			susfs_enable_log(user_arg);
		else
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
		if (cmd == CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG)
			susfs_set_cmdline_or_bootconfig(user_arg);
		else
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
		if (cmd == CMD_SUSFS_ADD_OPEN_REDIRECT)
			susfs_add_open_redirect(user_arg);
		else
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MAP
		if (cmd == CMD_SUSFS_ADD_SUS_MAP)
			susfs_add_sus_map(user_arg);
		else
#endif
		if (cmd == CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING)
			susfs_set_avc_log_spoofing(user_arg);
		else if (cmd == CMD_SUSFS_SHOW_ENABLED_FEATURES)
			susfs_get_enabled_features(user_arg);
		else if (cmd == CMD_SUSFS_SHOW_VARIANT)
			susfs_show_variant(user_arg);
		else if (cmd == CMD_SUSFS_SHOW_VERSION)
			susfs_show_version(user_arg);
		return 0;
	}
#endif
'''
replace(
    root / "supercalls.c",
    "\tunsigned long reply = (unsigned long)arg4;\n\n"
    "\t/* Check if this is a request to install KSU fd */",
    "\tunsigned long reply = (unsigned long)arg4;\n" + dispatcher +
    "\n\t/* Check if this is a request to install KSU fd */",
    "supercalls.c SUSFS dispatcher",
)

replace(
    root / "selinux/selinux.c",
    "bool is_ksu_domain(void)\n"
    "{\n"
    "    return is_task_ksu_domain(current_cred());\n"
    "}\n",
    "bool is_ksu_domain(void)\n"
    "{\n"
    "    return is_task_ksu_domain(current_cred());\n"
    "}\n\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "bool susfs_is_current_ksu_domain(void)\n"
    "{\n"
    "    return is_ksu_domain();\n"
    "}\n"
    "#endif\n",
    "SELinux SUSFS domain adapter",
)

print(f"patched modern KernelSU Next SUSFS glue in {root}")
