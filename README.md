# Runbo E72 万科物业版 玩机工具

专用万科物业定制的润博 E72 对讲机（WKWY）。

机器到手一堆毛病：电话打不出去（拨号秒挂）、装软件要输密码、自己换的壁纸一重启就被还原、浏览器莫名其妙没了。折腾一圈把根都挖出来了。

纯 adb 的 pm / setprop / settings 操作，不动系统分区，随时可以改回去。不想看原理的直接拿 `dist/RadioFixTool.exe` 用，自带 adb 免安装。

## 挖出来的根

* **拨号秒挂** —— 元凶是 `com.runbo.sdk_service`。通话建立时读 Settings.Secure 里的 phone_whitelist_size / phone_whitelist_backups，跟库里的对不上就 endCall()，所以拨谁的号都是秒挂。停用即可。
* **壁纸还原、浏览器被禁** —— `com.tintele.DoDefaultSetting`。开机广播里 setWallpaper() 强设内置图，顺手 disableApplication 掉浏览器、短信、快速搜索。所以手动打开也没用，下次开机又被禁回去。停用 + pm enable 恢复。
* **装软件要密码** —— 最有意思的一个。安装总闸是 `sys.appinstall.state`，非持久属性，重启清零。厂商本意是 settings 里的 RestoreDataReceiver 开机把它同步回来，但它先 startActivity 到 `runbo.android.poc` 的登录页——这个包机器上根本没有，ActivityNotFoundException 直接把 onReceive 后面的同步代码炸断，所以授权永远恢复不了。补一个同包名的空壳 APK（Theme.NoDisplay，起来就 finish，用户看不到）让链路跑通就行，源码在 `placeholder-apk/`。
* **VoLTE** —— `setprop persist.sys.volte.enable true`，就一行。

全部可以改回去：

```
adb shell pm enable com.runbo.sdk_service
adb shell pm enable com.tintele.DoDefaultSetting
adb uninstall runbo.android.poc
adb shell setprop sys.appinstall.state 0
adb reboot
```

注意：要装回原厂 POC 对讲应用前，先 `adb uninstall runbo.android.poc`，不然签名冲突装不上。

## 用法

1. 对讲机开 USB 调试（设置 → 关于手机 → 连点版本号5次）
2. 插电脑，设备上点"允许 USB 调试"
3. 跑 `dist/RadioFixTool.exe`，设备出来后点开始修复，完事自动重启

Win10/11 一般免驱。杀毒报"未知程序"是自编译没签名，加个信任就行。

## 源码

```
src/app.py         主程序。标准库零依赖，本地起 HTTP 服务，调 Edge/Chrome 的 --app 模式当界面
src/ui.html        界面就这一个 html
placeholder-apk/   上面说的空壳 APK。smali 是手写的，就一个 onCreate 里直接 finish 的 Activity
adb-windows/       打包 exe 用的 adb（platform-tools 原装）
docs/              给非程序员的纯中文说明
```

重新打包 exe（PyInstaller）：

```
cd src
pip install pyinstaller
python -m PyInstaller --onefile --noconsole RadioFixTool.spec
```

spec 引用 `../adb-windows/` 和本目录的 placeholder.apk，产物在 `dist/`。

重打占位包：

```
cd placeholder-apk
bash build.sh
```

需要 aapt2 / zipalign / apksigner、android.jar、smali-fat.jar、JDK 17。路径不在我这台机器上的，用环境变量改：`BT`、`AJAR`、`SMALI`、`JHOME`、`KS`。

## 已知情况

* 同批次展讯 SC9850 / Android 8.1 的定制机应该都能用；别的机型没这些组件的话对应步骤自动跳过，不会出事
* 只在 Windows 下跑过。这台 ROM 的 su 能拿 uid=0 但 SELinux 还锁在 shell 域，写不了系统分区，所以干脆全走可逆设置，也没打算去碰 root

## 丑话说在前面

仅供设备的个人所有者恢复自己机器的正常功能，别拿去规避单位合法的设备管理。操作虽然可逆，搞挂了别找我。MIT License。
