# Runbo E72 万科物业定制版修复工具

> **English**: A one-click repair tool for the Runbo E72 (Vanke Property custom edition) POC radio — fixes instant call hang-up, wallpaper reset on boot and disabled system apps, and restores password-free APK installation. Pure reversible adb tweaks, no flashing, no root writes.

一款给 **润博（Runbo）E72 万科物业定制版对讲机** 做的一键修复 / 解锁工具，绿色免安装，自带 adb，连上 USB 点一下即可完成全部修复。**全程只做可逆的系统设置，不刷机、不改系统分区。**

> 同批次展讯 SC9850 / Android 8.1 定制对讲机也可使用。其他机型运行也不会报错——本机没有对应组件时相关步骤会自动跳过。

## 它解决什么问题

万科物业定制的 ROM 对系统做了不少"管控"，这台机器拿来个人使用会非常难受。本工具针对以下痛点逐一修复：

| 问题 | 元凶 | 修复方式 |
|---|---|---|
| **拨号秒挂**：一点拨号瞬间被挂断 | `com.runbo.sdk_service` 通话时比对白名单，号码不匹配直接 `endCall()` | 停用该服务 |
| **壁纸开机被还原** | `com.tintele.DoDefaultSetting` 开机广播里强设内置壁纸 | 停用该组件 |
| **浏览器 / 短信 / 搜索被禁用**，手动打开也会被改回去 | 同上组件开机时 `disableApplication()` | 重新启用这三个系统应用 |
| **装软件要输密码**（WKWY1234），重启后授权失效 | framework 读取非持久属性 `sys.appinstall.state`，负责开机恢复的 `RestoreDataReceiver` 启动一个不存在的包 `runbo.android.poc` 时抛异常中断 | 置位授权属性 + 安装一个同包名占位组件，让开机流程跑通 |
| VoLTE 未开启 | 系统属性默认关闭 | `setprop persist.sys.volte.enable true` |

其中"安装授权"问题的定位过程比较有意思，值得展开说：

- 该 ROM 的安装总闸是 `sys.appinstall.state`，**非持久属性，重启即清零**；
- 厂商本来的设计是设置里的 `RestoreDataReceiver` 开机把它同步回来，但恢复入口会先 `startActivity` 到 `runbo.android.poc` 的登录页，**这个包在机器上根本不存在**，`ActivityNotFoundException` 直接把后面的同步代码炸断；
- 所以只要补装一个同包名、只含一个 `Theme.NoDisplay` 空页面的占位 APK（本仓库 `placeholder-apk/` 有完整源码），开机链路就能跑通，授权自动恢复，**装软件从此不需要密码**。

## 使用方法

1. 电脑装好 adb 驱动（Win10/11 一般自动识别）
2. 对讲机：设置 → 关于手机 → 连续点「版本号」7 次 → 开发者选项 → 打开「USB 调试」
3. 数据线连电脑，设备上弹窗点「允许 USB 调试」
4. 双击运行 `dist/RadioFixTool.exe`（改名不影响使用）
5. 顶部出现设备型号和状态徽章后，点「开始一键修复」
6. 完成后工具自动重启设备，约 1 分钟重新开机

> 工具已内嵌 adb 与全部依赖，无需安装任何其他东西。杀毒软件提示「未知程序」属正常现象（自编译无数字签名），加信任即可。

## 恢复原厂状态

返修或需要装原厂 POC 对讲应用时：

```bash
adb shell pm enable com.runbo.sdk_service
adb shell pm enable com.tintele.DoDefaultSetting
adb uninstall runbo.android.poc
adb shell setprop sys.appinstall.state 0
adb reboot
```

> 注意：以后要安装原厂 POC/POT 应用前，先 `adb uninstall runbo.android.poc`，否则会因签名冲突装不上。

## 目录结构

```
├── dist/
│   └── RadioFixTool.exe        # 编译好的成品（也可作为 GitHub Release 附件发布）
├── src/                        # 主程序源码
│   ├── app.py                  # 本地 HTTP 服务 + 修复逻辑（纯标准库，零依赖）
│   ├── ui.html                 # 单页界面，由 Edge/Chrome 以 --app 模式显示
│   ├── gen_icon.py             # 纯 Python 生成图标
│   ├── icon.ico
│   ├── placeholder.apk         # 授权引导组件（打包进 exe）
│   └── RadioFixTool.spec       # PyInstaller 打包配置
├── placeholder-apk/            # 占位 APK 完整源码
│   ├── AndroidManifest.xml     # 包名 runbo.android.poc
│   ├── smali/                  # 手写字节码（仅一个立即 finish 的空 Activity）
│   └── build.sh                # aapt2 → smali → zip → zipalign → apksigner
└── adb-windows/                # 打包用的 adb（取自 Android SDK platform-tools）
```

## 工作原理

- 主程序启动后把内嵌资源释放到 `%LOCALAPPDATA%\RadioFixTool\`，在 `127.0.0.1` 随机端口起一个本地 HTTP 服务，并用 Edge/Chrome 的 `--app` 模式打开界面窗口；
- 界面通过 `/api/devices`、`/api/status`、`/api/fix`、`/api/log` 等接口与后端交互，修复逻辑全部基于 **adb 的 `pm` / `settings` / `setprop`** 命令；
- 这台 ROM 的 `su` 虽然能拿到 uid=0，但 SELinux 仍限制在 shell 域写不了系统分区，所以工具刻意避开 root 写入，全部走可逆设置，随时可以恢复。

## 从源码构建

### 打包 exe

```bash
cd src
pip install pyinstaller
python -m PyInstaller --onefile --noconsole --clean ^
    --name RadioFixTool --icon icon.ico ^
    --add-binary "../adb-windows/adb.exe;." ^
    --add-binary "../adb-windows/AdbWinApi.dll;." ^
    --add-binary "../adb-windows/AdbWinUsbApi.dll;." ^
    --add-binary "../adb-windows/libwinpthread-1.dll;." ^
    --add-data "placeholder.apk;." ^
    --add-data "ui.html;." ^
    app.py
```

产物在 `dist/RadioFixTool.exe`。

### 构建 placeholder.apk

```bash
cd placeholder-apk
bash build.sh
```

需要 Android SDK build-tools、android.jar、smali-fat.jar 和 JDK 17，路径可通过环境变量 `BT` / `AJAR` / `SMALI` / `JHOME` 覆盖（见脚本头部）。

## 免责声明

本项目仅供所购设备的个人所有者恢复设备的正常使用功能。请遵守当地的法律法规及设备所属组织的管理规定，勿用于规避合法设备管理的用途。使用本工具的一切后果由使用者自行承担。完整声明见 [DISCLAIMER.md](DISCLAIMER.md)。

## License

[MIT](LICENSE)
