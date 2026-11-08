# K90 YARP 现成镜像解包分析

分析对象：
`YARP-4.0.0-16-sm8750-gui2-only-2026-10-29-0201.img`（用户提供的"K90 的"镜像）

## 结论（推翻前面的方案）

**这不是 K90(annibale) 的单机型 recovery，而是 SM8750 平台统一树，warsaw / REDMI K90 Ultra 是内置的一等 SKU，而且开发者的真机调试基准就是 warsaw。**

因此：**不需要"改成 YARP"，不需要新建 warsaw 设备树，也不需要编译 95 GiB 源码。这个镜像直接就能用在 K90 至尊版上。** 本目录里的 `BoardConfig.mk` 等设备树骨架降级为"解包参考资料 + 将来要自建树时的模板"，不再是必须构建的目标。

用户所说的"有人证实两个机型通用"，实际情况比"部分通用"更强：K90 和 K90 至尊共用的是**同一个镜像**，差异由启动时的 SKU 分流处理。

## 镜像技术参数

| 项目 | 值 |
|---|---|
| 文件大小 | 104857600 (100 MiB，按分区大小补齐) |
| Boot header | v4，`header_size=1584`，`os_version=0xc75d263c` |
| `kernel_size` | **0** —— ramdisk-only，内核来自设备 `vendor_boot`，不是完整 boot 镜像 |
| `ramdisk_size` | 60888049 (58 MiB)，lz4_legacy，17 个块 |
| 解压后 cpio | 139602944 字节，1273 个条目 |
| ramdisk 偏移 | 4096（v4 按 4096 页对齐） |
| cmdline | 空 |
| GUI | `libgui2.so` 1.47 MB，GUI2/LVGL 已在包内 |

## SKU 分流机制

```
ro.boot.hardware.sku  (bootloader 通过 cmdline 传入)
  -> init.recovery.qcom.rc : import /platform/sku/${sku}.rc
  -> platform/sku/warsaw.rc -> import /platform/sm8750/init
  -> platform/sm8750/early.sh 把 overlay 铺到根目录
  -> weaver-vendor.sh 按 sku 决定 ro.twrp.weaver
  -> variant-script.sh 按 sku 设机型属性，并复制 /odm/variant/<sku>/odm/* 到 /odm
  -> 置 twrp.variant.files_copied=1，触发 weaver / 触摸 / 震动 HAL 启动
```

内置 SKU 共 7 个：`warsaw`、`annibale`、`miro`、`dada`、`haotian`、`xuanyuan`、`piano`。

## 镜像里"咱们 K90 至尊的东西"（已存在，无需补）

| 位置 | 内容 |
|---|---|
| `platform/sku/warsaw.rc` | warsaw 的 SKU 入口 |
| `variant-script.sh` 的 `"warsaw")` 分支 | `model="REDMI K90 Ultra"`、`ro.twrp.device_version="REDMI_K90_Ultra"`、`ro.twrp.wlan_chip="kiwi_v2"`、`vendor.display.enable_spr=1` + `spr_bypass=1`、震动 170/35、`/sys/class/qcom-haptics` |
| `odm/bin/variant-script.sh` 注释 | "Measured on warsaw with device_type ff: 4s with it on, 1s with it off"、"Measured on warsaw: agm 24s to register IVibrator, ff 1s" |
| `platform/sm8750/overlay/odm/variant/warsaw/odm/firmware/` | `goodix_firmware_warsaw.bin` (223744 B)、`goodix_cfg_group_warsaw.bin`、`warsaw_gtp_thp_config.ini`、film/glove/water tflite 模型、各 test_limits CSV |
| 同目录 `odm/lib64/` | warsaw 专属 `libtouchreport.so` / `_alg.so` / `_hal.so` / `_sensor.so`、`libaachaptics.so`（与 annibale 的 `libtouchreport_alg_goodix.so` / `_2.so` 不同） |
| `weaver-vendor.sh` | `warsaw | annibale | miro) vendor="nxp"` —— 决定 Weaver/eSE 走 NXP 链 |
| `init.recovery.sm8750.rc` 注释 | "lsmod on warsaw shows qcom_hv_haptics loaded from vendor_dlkm"、"measured on warsaw: every HAL lookup then fails" |

## 解密链（已完整打包，非半成品）

- `recovery.fstab`（统一树共用）：`/data` = f2fs，`fileencryption=aes-256-xts:aes-256-cts:v2+inlinecrypt_optimized+wrappedkey_v0`，`keydirectory=/metadata/vold/metadata_encryption`，`metadata_encryption=aes-256-xts:wrappedkey_v0`；`/metadata` 为 `first_stage_mount`。
- VINTF：`android.hardware.security.keymint-service-qti.xml`、`android.hardware.weaver-service.xml`、`android.system.keystore2-service.xml`、`se_omapi.xml`。
- HAL 二进制：`qseecomd`、`android.hardware.gatekeeper-service-qti`、`android.hardware.security.keymint-service-qti`、三套 weaver 实现，均在 `platform/sm8750/overlay/{vendor,odm}/bin/hw/`。
- `prepdecrypt.sh` (15.7 KB)：在 KeyMint 构造前把版本属性指向已安装系统，这是跨 Android 16/17 升级场景的关键适配。
- `libgui2.so` + KeyMint V3/V4、gatekeeper V1、weaver V2 的 NDK 库齐全。

对比之下，原来的 `wumisc/twrp_device_xiaomi_warsaw` 树缺 `TW_INCLUDE_CRYPTO`、`TW_INCLUDE_FBE_METADATA_DECRYPT`、`BOARD_USES_METADATA_PARTITION`、`TW_USE_FSCRYPT_POLICY`、vendor HAL 和 VINTF，基本不可能解密 —— 那个方向确实该放弃。

## 刷机前必须确认的一件事

**`ro.boot.hardware.sku` 必须等于 `warsaw`。** 全部差异都靠它分发。

```bash
adb shell getprop ro.boot.hardware.sku
adb shell cat /proc/cmdline | tr ' ' '\n' | grep -i hardware.sku
```

若不是 `warsaw`，`variant-script.sh` 会落入 default 分支（`model="SM8750"`），`/odm/variant/<sku>/odm` 不存在时保持 base odm —— 触摸固件、震动、weaver 都不会按 warsaw 加载。此时不要直接刷，先在 init 里加 SKU 映射。

## 建议操作流程

1. 备份原厂 `boot` / `vendor_boot` / `dtbo` 及 `recovery_a`、`recovery_b`。
2. 先 `fastboot boot <img>` 临时引导，**不要首刷**。这是 ramdisk-only 镜像（无内核），必须刷到 recovery 分区而不是当 boot.img 用。
3. 进 recovery 后核对：`getprop ro.twrp.device_version` 应为 `REDMI_K90_Ultra`，`getprop ro.product.model` 应为 `REDMI K90 Ultra`，`getprop ro.twrp.weaver` 应为 `nxp`。
4. 检查显示、触摸、ADB、`/tmp/recovery.log`，再验证 `/data` 解密。
5. 确认无误后双槽刷入 `recovery_a` / `recovery_b`，必要时处理 AVB 回滚。

## 风险与未验证项

- 镜像基线 `YARP-4.0.0-16`（Android 16，2026-10-29）。若机器已升 HyperOS 4 / Android 17，`prepdecrypt.sh` 设计上会适配已装系统版本，但**真机解密结果无法从静态分析确认**，必须实机验证。
- 本报告只做静态解包，没有在任何设备上引导过该镜像。
- 若解密失败，抓取 `/tmp/recovery.log` + `dmesg` + `getprop | grep init.svc`，重点看 `qseecomd` / `gatekeeper` / `keymint` / `weaver_nxp` 是否起来。

## 解包产物

`k90-reference/` 内：`filelist.txt`（1273 条完整清单）、`report.txt` / `report.json`（概览）、`configs/`（87 个小文本配置，含 init.rc、fstab、VINTF、variant-script、weaver-vendor 等）。二进制只记录路径与大小，未落盘。

复现命令：

```bash
pip install lz4
python3 scripts/inspect-yarp-image.py <recovery.img> k90-reference
```
