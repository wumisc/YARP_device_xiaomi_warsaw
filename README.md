# YARP recovery for REDMI K90 Ultra (warsaw) · SM8750

本仓库现在只做一件事：**用 GitHub Actions 从上游源码编译最新的 YARP（TWRP 16 / GUI2）recovery，给红米 K90 至尊版用。**

原来的 `BoardConfig.mk` / `device.mk` / `recovery.fstab` 等文件是从 SM8750 通用树抄来的半成品（缺内核、vendor blobs、解密链与 VINTF，从未编译或真机验证），**已废弃，保留仅作历史参考**。不要再用它们构建。

## 结论：不需要为 warsaw 单独做设备树

`lingqiqi5211/twrp_device_xiaomi_sm8750_sm8850` 是 **SM8750 / SM8850 统一树**，一个平台一份镜像，开机时按 `ro.boot.hardware.sku` 选择机型。其 README 明确写着 *Hardware testing on this branch includes `warsaw` and `piano`* —— warsaw 是硬件验证过的机型，不是"借用 K90 的配置"。

内置 SKU：

| SKU | 机型 | Weaver | WLAN |
| --- | --- | --- | --- |
| `dada` | Xiaomi 15 | Thales eSE | peach_v2 |
| `haotian` | Xiaomi 15 Pro | Thales eSE | peach_v2 |
| `xuanyuan` | Xiaomi 15 Ultra | Thales eSE | peach_v2 |
| **`warsaw`** | **REDMI K90 Ultra** | **NXP eSE** | **kiwi_v2** |
| `annibale` | REDMI K90 / POCO F8 Pro | NXP eSE | kiwi_v2 |
| `miro` | REDMI K80 Pro / POCO F7 Ultra | NXP eSE | detected |
| `piano` | Xiaomi Pad 8 Pro | TEE (miweaver) | peach_v2 |

warsaw 专属内容（触摸固件 `goodix_firmware_warsaw.bin`、`warsaw_gtp_thp_config.ini`、warsaw 版 `libtouchreport*.so`、震动与显示参数、NXP Weaver 解密链）都在统一树内，由 `variant-script.sh` + `weaver-vendor.sh` 在启动时分发。

现成镜像 `YARP-4.0.0-16-sm8750-gui2-only-2026-10-29-0201.img` 的完整解包分析见 [IMAGE-ANALYSIS.md](IMAGE-ANALYSIS.md)：boot header v4、`kernel_size=0`（**ramdisk-only，内核来自设备 `vendor_boot`**）、1273 个 ramdisk 条目、含 `platform/sku/warsaw.rc`。

## 一键编译

**Actions → Build YARP recovery (warsaw / SM8750) → Run workflow**

- 触发方式：手动、`sources.json` / `scripts/build.sh` / workflow 变更时自动、每周一 04:00 UTC 定时（拉最新上游源码）。
- 手动触发可勾选「Publish the image to GitHub Releases as well」，默认只传 artifact。
- 产物 artifact `YARP-warsaw-<run_id>`：`YARP-16-sm8750-warsaw-<sha7>-recovery.img`、`SHA256SUMS.txt`、`verification.json`、`source-manifest.xml`、`sources.json`；另有独立日志 artifact。
- 打包前会校验镜像：`ANDROID!` magic、header v4、`kernel_size=0`、ramdisk 非空，不通过直接失败。

源码固定在 [`sources.json`](sources.json)，当前锁定：

| 项目 | 分支 / revision |
| --- | --- |
| `TWRP-Test/platform_manifest_twrp_aosp` | `814b553116ceedde197f70389cff9661d81d8337` |
| `TWRP-Test/android_bootable_recovery` | `a93a12ec107265ab9c3c7fe3e4f96c8740a01337` |
| `TWRP-Test/android_build_soong` | `95e4cb167d65d5f2a034f1eeac73a920adebc09d` |
| `TWRP-Test/android_external_lvgl` | `992dd52fc5112b24845078ea60c1cf1e2e27c5b5` |
| `TWRP-Test/android_external_libvpx` | `f42506c3faf4592a9d8929c9ca832fd72fff94a0` |
| `TWRP-Test/android_external_libwebm` | `99fcd14602ba76998d086b602f29a243e1d5c835` |
| `lingqiqi5211/twrp_device_xiaomi_sm8750_sm8850` | `583bd15f1381fb14dc4d4a8252a0a3f36cba16e8` |

要编译"更新"的版本，改 `sources.json` 里的 revision 再跑一次即可；定时构建会沿用锁定版本，保证可复现。

CI 需要约 95 GiB 源码 + 15 GiB 输出，工作流会清掉 runner 预装 SDK、分配 16 GiB swap、用 cgroup 限制编译内存（11G high / 13G max），单次构建 2–6 小时、`timeout-minutes: 360`。工作流结构参照已成功出图的 `MDXRosmontis/yarp-sm8850`，但**本仓库的首轮构建尚未实机跑通**，第一次运行请留意 `sync.log` 与 `build.log`。

## 本地编译

```bash
mkdir -p /build/yarp && cd /build/yarp
repo init -u https://github.com/TWRP-Test/platform_manifest_twrp_aosp.git -b twrp-16.0 --depth=1
repo sync -c -j8
git clone -b twrp-16.0 \
  https://github.com/lingqiqi5211/twrp_device_xiaomi_sm8750_sm8850.git \
  device/xiaomi/sm8750
source build/envsetup.sh
export YARP_PLATFORM=sm8750
lunch twrp_sm8750-bp2a-eng
mka installclean          # GUI2 要求，跨平台复用 out 目录时必做
mka recoveryimage
# 产物：out/target/product/sm8750/recovery.img
```

`YARP_PLATFORM=sm8750` 是必须的；同一 lunch 目标也用于 SM8850，靠这个变量选择打包哪套平台层。

## 刷入前必查

```bash
adb shell getprop ro.boot.hardware.sku
```

**必须返回 `warsaw`。** 全部机型差异都靠它分发；若命中 default 分支，机型会显示 `SM8750`，warsaw 的触摸固件、震动与 Weaver 都不会加载。

## 刷入与验证

1. 备份原厂 `boot` / `vendor_boot` / `dtbo` 与 `recovery_a`、`recovery_b`。
2. 本镜像是 **ramdisk-only**（不含内核），内核由设备 `vendor_boot` 提供；刷到 recovery 分区，不要当 `boot.img` 用。
3. 先临时引导，不要首刷：
   ```bash
   fastboot boot YARP-16-sm8750-warsaw-*-recovery.img
   ```
4. 进 recovery 后核对：
   ```bash
   adb shell getprop ro.boot.hardware.sku        # warsaw
   adb shell getprop ro.twrp.device_version      # REDMI_K90_Ultra
   adb shell getprop ro.product.model            # REDMI K90 Ultra
   adb shell getprop ro.twrp.weaver              # nxp
   ```
5. 检查显示、触摸、ADB、`/tmp/recovery.log`，再验证 `/data` 解密。
6. 确认无误后双槽刷入 `recovery_a` / `recovery_b`；若官方 recovery 被回滚，再处理 AVB。

解密链依赖当前系统的 vendor 加密栈。若已升级到 HyperOS 4 / Android 17，统一树的 `prepdecrypt.sh` 会在 KeyMint 启动前把版本属性指向已安装系统，但**结果只能真机验证**。解密失败时抓 `/tmp/recovery.log`、`dmesg` 和 `getprop | grep init.svc`，重点看 `qseecomd` / `gatekeeper` / `keymint` / `weaver_nxp`。

## 工具

- `scripts/inspect-yarp-image.py`：解包现成 `recovery.img`（v4 header + lz4_legacy + cpio newc），导出文件清单和小文本配置，不改动原镜像。
  ```bash
  pip install lz4
  python3 scripts/inspect-yarp-image.py recovery.img k90-reference
  ```
- `scripts/build.sh`：CI 用的 `sync` / `build` / `package` 三段式构建脚本。
- `IMAGE-ANALYSIS.md`：现成镜像的解包分析、SKU 分流机制、warsaw 专属文件清单。

## Sources / 致谢

- 统一设备树：[lingqiqi5211/twrp_device_xiaomi_sm8750_sm8850](https://github.com/lingqiqi5211/twrp_device_xiaomi_sm8750_sm8850) `twrp-16.0`
- YARP / TWRP 16 GUI2 源码与 manifest：[TWRP-Test](https://github.com/TWRP-Test) `twrp-16.0`
- CI 结构参考：[MDXRosmontis/yarp-sm8850](https://github.com/MDXRosmontis/yarp-sm8850)、[MasterOfStar/YARP-nx729j](https://github.com/MasterOfStar/YARP-nx729j)
- 上游通用树：[YuKongA/twrp_device_xiaomi_sm8750_thales](https://github.com/YuKongA/twrp_device_xiaomi_sm8750_thales)

> 本仓库产物仅供开发与测试，刷机风险自负。任何构建都未在本仓库做过真机引导验证。
