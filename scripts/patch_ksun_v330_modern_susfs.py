#!/usr/bin/env python3
"""Add narrow SUSFS glue to the pinned KernelSU Next v3.3.0 tree."""

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
required = (
    "Kconfig",
    "core/init.c",
    "extras.c",
    "hook/setuid_hook.c",
    "policy/feature.h",
    "supercall/dispatch.c",
    "supercall/supercall.c",
    "selinux/selinux.c",
)
if not all((root / name).is_file() for name in required):
    raise SystemExit(f"not a KernelSU Next v3.3 kernel directory: {root}")

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
    root / "core/init.c",
    '#include "infra/symbol_resolver.h"\n',
    '#include "infra/symbol_resolver.h"\n'
    "#ifdef CONFIG_KSU_SUSFS\n"
    "#include <linux/susfs.h>\n"
    "#endif\n",
    "core SUSFS include",
)
replace(
    root / "core/init.c",
    "\tksu_feature_init();\n\n\tksu_sulog_init();",
    "\tksu_feature_init();\n\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "\tsusfs_init();\n"
    "#endif\n\n"
    "\tksu_sulog_init();",
    "core SUSFS initialization",
)

replace(
    root / "hook/setuid_hook.c",
    '#include "feature/kernel_umount.h"\n',
    '#include "feature/kernel_umount.h"\n'
    "#ifdef CONFIG_KSU_SUSFS\n"
    "#include <linux/susfs_def.h>\n"
    '#include "selinux/selinux.h"\n\n'
    "#ifdef CONFIG_KSU_SUSFS_SUS_PATH\n"
    "extern void susfs_run_sus_path_loop(void);\n"
    "#endif\n"
    "#endif\n",
    "setuid SUSFS declarations",
)
replace(
    root / "hook/setuid_hook.c",
    "    // we rely on the fact that zygote always call setresuid(3) with same uids\n\n"
    '    pr_info("handle_setresuid from %d to %d\\n", old_uid, new_uid);',
    "    // we rely on the fact that zygote always call setresuid(3) with same uids\n\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "    bool susfs_zygote = is_zygote(current_cred());\n"
    "#endif\n\n"
    '    pr_info("handle_setresuid from %d to %d\\n", old_uid, new_uid);',
    "setuid zygote gate",
)
replace(
    root / "hook/setuid_hook.c",
    "    // Handle kernel umount\n"
    "    ksu_handle_umount(old_uid, new_uid);\n\n"
    "    return 0;\n",
    "#ifdef CONFIG_KSU_SUSFS\n"
    "    if (susfs_zygote &&\n"
    "        (is_isolated_process(new_uid) ||\n"
    "         (is_appuid(new_uid) && ksu_uid_should_umount(new_uid))))\n"
    "        goto do_umount;\n"
    "#endif\n\n"
    "    ksu_handle_umount(old_uid, new_uid);\n"
    "\n"
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
    "setuid SUSFS umount path",
)

replace(
    root / "supercall/supercall.c",
    '#include "manager/manager_identity.h"\n',
    '#include "manager/manager_identity.h"\n'
    "#ifdef CONFIG_KSU_SUSFS\n"
    "#include <linux/susfs.h>\n"
    '#include "policy/feature.h"\n'
    "#endif\n",
    "supercall SUSFS includes",
)

susfs_adapter = r'''

#ifdef CONFIG_KSU_SUSFS
static void ksu_susfs_set_avc_log_spoofing(void __user **user_info)
{
	struct st_susfs_avc_log_spoofing info = { 0 };

	if (copy_from_user(&info,
			   (struct st_susfs_avc_log_spoofing __user *)
				   *user_info,
			   sizeof(info))) {
		info.err = -EFAULT;
	} else {
		info.err = ksu_set_feature(KSU_FEATURE_AVC_SPOOF,
					 info.enabled ? 1 : 0);
	}

	if (copy_to_user(
		    (struct st_susfs_avc_log_spoofing __user *)*user_info,
		    &info, sizeof(info)))
		pr_warn("SUSFS AVC reply failed\n");
}
#endif
'''
replace(
    root / "supercall/supercall.c",
    "uint32_t ksuver_override = 0;\n",
    "uint32_t ksuver_override = 0;\n" + susfs_adapter,
    "supercall SUSFS AVC adapter",
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
            ksu_susfs_set_avc_log_spoofing(user_arg);
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
    root / "supercall/supercall.c",
    "    unsigned long reply = (unsigned long)arg4;\n\n"
    "    /* Check if this is a request to install KSU fd */",
    "    unsigned long reply = (unsigned long)arg4;\n" + dispatcher +
    "\n    /* Check if this is a request to install KSU fd */",
    "supercall SUSFS dispatcher",
)

replace(
    root / "supercall/dispatch.c",
    "    strscpy(cmd.tag, KERNEL_SU_VERSION_TAG, sizeof(cmd.tag));\n",
    "#ifdef CONFIG_KSU_SUSFS\n"
    '    strscpy(cmd.tag, KERNEL_SU_VERSION_TAG "-modern-susfs",\n'
    "            sizeof(cmd.tag));\n"
    "#else\n"
    "    strscpy(cmd.tag, KERNEL_SU_VERSION_TAG, sizeof(cmd.tag));\n"
    "#endif\n",
    "modern SUSFS version tag",
)

replace(
    root / "extras.c",
    '#include "infra/seccomp_cache.h"\n',
    '#include "infra/seccomp_cache.h"\n'
    "#ifdef CONFIG_KSU_SUSFS\n"
    "#include <linux/jump_label.h>\n"
    "extern struct static_key_false susfs_is_avc_log_spoofing_enabled;\n"
    "#endif\n",
    "AVC SUSFS declaration",
)
replace(
    root / "extras.c",
    "static int avc_spoof_feature_get(u64 *value)\n"
    "{\n"
    "\t*value = ksu_avc_spoof_enabled ? 1 : 0;\n"
    "\treturn 0;\n"
    "}\n\n"
    "static int avc_spoof_feature_set(u64 value)\n"
    "{\n"
    "\tbool enable = value != 0;\n\n"
    "\tif (enable == ksu_avc_spoof_enabled) {\n"
    '\t\tpr_info("avc_spoof: no need to change\\n");\n'
    "\t\treturn 0;\n"
    "\t}\n\n"
    "\tksu_avc_spoof_enabled = enable;\n\n"
    "\tif (boot_completed) {\n"
    "\t\tif (enable) {\n"
    "\t\t\tksu_avc_spoof_enable();\n"
    "\t\t} else {\n"
    "\t\t\tksu_avc_spoof_disable();\n"
    "\t\t}\n"
    "\t}\n\n"
    '\tpr_info("avc_spoof: set to %d\\n", enable);\n\n'
    "\treturn 0;\n"
    "}\n",
    "static int avc_spoof_feature_get(u64 *value)\n"
    "{\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "\t*value = static_branch_likely(\n"
    "\t\t&susfs_is_avc_log_spoofing_enabled) ? 1 : 0;\n"
    "#else\n"
    "\t*value = ksu_avc_spoof_enabled ? 1 : 0;\n"
    "#endif\n"
    "\treturn 0;\n"
    "}\n\n"
    "static int avc_spoof_feature_set(u64 value)\n"
    "{\n"
    "\tbool enable = value != 0;\n"
    "\tbool changed = enable != ksu_avc_spoof_enabled;\n\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "\tbool susfs_enabled = static_branch_likely(\n"
    "\t\t&susfs_is_avc_log_spoofing_enabled);\n\n"
    "\tif (enable != susfs_enabled) {\n"
    "\t\tif (enable)\n"
    "\t\t\tstatic_branch_enable(\n"
    "\t\t\t\t&susfs_is_avc_log_spoofing_enabled);\n"
    "\t\telse\n"
    "\t\t\tstatic_branch_disable(\n"
    "\t\t\t\t&susfs_is_avc_log_spoofing_enabled);\n"
    "\t}\n"
    "#endif\n\n"
    "\tksu_avc_spoof_enabled = enable;\n"
    "\tif (changed && boot_completed) {\n"
    "\t\tif (enable)\n"
    "\t\t\tksu_avc_spoof_enable();\n"
    "\t\telse\n"
    "\t\t\tksu_avc_spoof_disable();\n"
    "\t}\n\n"
    '\tpr_info("avc_spoof: set KSU and SUSFS to %d\\n", enable);\n'
    "\treturn 0;\n"
    "}\n",
    "AVC Feature bridge",
)
replace(
    root / "extras.c",
    "void ksu_avc_spoof_late_init(void)\n"
    "{\n"
    "\tboot_completed = true;\n"
    "\t\n"
    "    if (ksu_avc_spoof_enabled) {\n"
    "\t\tksu_avc_spoof_enable();\n"
    "\t}\n"
    "}\n",
    "void ksu_avc_spoof_late_init(void)\n"
    "{\n"
    "\tboot_completed = true;\n\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "\tif (ksu_avc_spoof_enabled &&\n"
    "\t    !static_branch_likely(\n"
    "\t\t    &susfs_is_avc_log_spoofing_enabled))\n"
    "\t\tstatic_branch_enable(\n"
    "\t\t\t&susfs_is_avc_log_spoofing_enabled);\n"
    "#endif\n\n"
    "\tif (ksu_avc_spoof_enabled)\n"
    "\t\tksu_avc_spoof_enable();\n"
    "}\n",
    "AVC late initialization",
)

replace(
    root / "selinux/selinux.c",
    "u32 ksu_file_sid __read_mostly = 0;\n",
    "u32 ksu_file_sid __read_mostly = 0;\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "u32 susfs_ksu_sid __read_mostly;\n"
    "u32 susfs_priv_app_sid __read_mostly;\n"
    "#endif\n",
    "SELinux SUSFS SID storage",
)
replace(
    root / "selinux/selinux.c",
    "    } else {\n"
    '        pr_info("Cached su SID: %u\\n", cached_su_sid);\n'
    "    }\n\n"
    "    err = security_secctx_to_secid(ZYGOTE_CONTEXT, strlen(ZYGOTE_CONTEXT),",
    "    } else {\n"
    '        pr_info("Cached su SID: %u\\n", cached_su_sid);\n'
    "    }\n"
    "#ifdef CONFIG_KSU_SUSFS\n"
    "    susfs_ksu_sid = cached_su_sid;\n"
    "    err = security_secctx_to_secid(\n"
    '        "u:r:priv_app:s0:c512,c768",\n'
    '        strlen("u:r:priv_app:s0:c512,c768"), &susfs_priv_app_sid);\n'
    "    if (err) {\n"
    '        pr_warn("Failed to cache SUSFS priv_app SID: %d\\n", err);\n'
    "        susfs_priv_app_sid = 0;\n"
    "    }\n"
    "#endif\n\n"
    "    err = security_secctx_to_secid(ZYGOTE_CONTEXT, strlen(ZYGOTE_CONTEXT),",
    "SELinux SUSFS SID initialization",
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

print(f"patched KernelSU Next v3.3 modern SUSFS glue in {root}")
