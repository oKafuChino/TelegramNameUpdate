# ✨ TelegramNameUpdate

TelegramNameUpdate 是一个轻量的 Telegram Last Name 自动更新脚本。它会通过 Telegram API 定时修改账号Last Name，让 Last Name 显示当前时间、UTC 时区偏移、日期、温度和天气状态等。

项目自带终端管理面板，安装后输入 `tg` 即可管理登录、显示项、输出顺序、更新、日志、时区同步和卸载。

> 本项目适合 Debian / Ubuntu 等使用 `systemd` 的 Linux VPS。

## 🚀 功能

- 🕒 每分钟自动更新 Telegram Last Name
- 🌍 支持显示时间、UTC 时区偏移、日期、温度、天气 Emoji
- 🔀 支持自定义 Last Name 输出顺序
- 🔠 支持 Unicode 粗体数字显示
- 🌦️ 支持 wttr.in 天气数据
- ⚙️ 支持 systemd 后台运行和开机自启
- 🎛️ 支持终端管理面板
- 🔄 支持脚本自更新
- 🧹 支持一键卸载
- 🔐 代码目录和运行数据目录分离，降低权限风险

## 📦 安装

安装前先到 [Telegram API 页面](https://my.telegram.org) 获取 `api_id` 和 `api_hash`。

在 VPS 上执行：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main/install.sh)
```

安装完成后打开面板：

```bash
tg
```

首次使用请选择 `[1] 更新账号 Session`，按提示输入 `api_id`、`api_hash`、手机号和验证码。

## 📁 文件位置

安装后主要文件位置如下：

```text
/opt/tg_updater/          程序代码和 Python venv，root 拥有
/var/lib/tg_updater/      配置、API 凭证和 Telegram session，tg_updater 用户拥有
/etc/systemd/system/      systemd 服务文件
/usr/local/bin/tg         管理面板快捷命令
```

敏感文件包括：

```text
/var/lib/tg_updater/api_auth.json
/var/lib/tg_updater/api_auth.session
/var/lib/tg_updater/api_auth.session-journal
```

这些文件会被设置为 `600` 权限。

## 🎛️ 面板选项

```text
[1]  更新账号 Session      重新登录或更换账号
[2]  查看运行日志          查看最近 50 条 systemd 日志

[3]  显示时间
[4]  显示时区              显示为 UTC+8 / UTC-5 等格式
[5]  显示日期
[6]  显示温度
[7]  显示天气
[8]  粗体显示
[9]  设置地区
[10] 输出顺序              自定义 Last Name 字段顺序
[11] 一键开启全部

[12] 重启后台服务
[13] 检查并更新
[14] 同步服务器时区

[99] 一键卸载脚本
[0]  退出管理面板
```

## 🔀 自定义输出顺序

选择 `[10] 输出顺序` 后，面板会显示可选字段：

```text
1. 时间
2. 时区
3. 日期
4. 温度
5. 天气
```

输入新顺序即可，例如：

```text
3,1,2,4,5
```

对应输出顺序：

```text
日期 > 时间 > 时区 > 温度 > 天气
```

显示开关和输出顺序是独立的。比如关闭了温度，即使顺序里包含温度，也不会输出温度。

## ⚙️ 配置示例

```json
{
  "show_time": true,
  "show_timezone": true,
  "show_date": false,
  "show_temp": true,
  "show_weather": true,
  "location": "Los Angeles",
  "use_bold": true,
  "name_order": [
    "time",
    "timezone",
    "date",
    "temp",
    "weather"
  ]
}
```

配置文件位置：

```text
/var/lib/tg_updater/config.json
```

## 🔄 更新

在面板中选择 `[13] 检查并更新`。

更新流程会：

- 从 GitHub 拉取 `tg_panel.py` 和 `tg_daemon.py`
- 下载到随机临时文件
- 检查 Python 语法
- 检查 `CURRENT_VERSION`
- 阻止低版本覆盖高版本
- 覆盖成功后重启后台服务

## 🧹 卸载

在面板中输入：

```text
99
```

然后输入：

```text
DELETE
```

卸载会删除：

```text
/opt/tg_updater
/var/lib/tg_updater
/usr/local/bin/tg
/usr/local/bin/tg_py
/etc/systemd/system/tg_name.service
```

注意：卸载会删除 Telegram 登录 session 和本地配置。


## 📝 更新日志

### 🛡️ v1.4.5

- 限制自更新和卸载只能在正式安装目录 `/opt/tg_updater` 执行
- 自更新临时文件改为写入目标目录，替换流程更稳
- 增强异常更新场景下的临时文件清理
- 自更新替换失败时会尝试恢复旧版本，避免半更新状态
- 增加地区名称长度限制和 API 凭证输入校验

### 🛡️ v1.4.4

- 加强配置文件类型校验，避免异常配置影响后台运行
- 自更新下载改用 Python 标准库，减少运行期对外部 `curl` 的依赖
- 安装时复用已有虚拟环境，并减少 pip 字节码生成
- systemd 服务增加最小权限加固，并禁用运行时字节码生成
- 配置保存后会提示后台服务重启是否成功

### ✨ v1.4.3

- 新增 `[99] 一键卸载脚本`
- 卸载前需要输入 `DELETE` 二次确认
- 卸载会停止服务并删除程序目录、运行数据目录、systemd 服务和快捷命令

### 🔐 v1.4.2

- 修复权限模型
- 代码目录 `/opt/tg_updater` 改为 root 拥有
- 运行数据目录迁移到 `/var/lib/tg_updater`
- 敏感文件权限设置为 `600`
- 自更新临时文件改为随机名称
- 下载脚本必须通过语法和版本校验
- 面板编号调整为连续顺序

### 🔄 v1.4.1

- 改进更新逻辑
- 下载后读取实际版本号
- 阻止低版本覆盖高版本
- 避免 GitHub Raw 缓存导致误降级

### 🔀 v1.4.0

- 新增 Last Name 输出顺序自定义
- 新增 `name_order` 配置项
- 面板新增输出顺序设置

### 🎨 v1.3.x

- 新增作者显示
- 新增彩色终端面板
- 新增 UTC 偏移时区显示
- 新增服务器时区同步
