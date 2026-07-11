# ✨ TelegramNameUpdate

TelegramNameUpdate 是一个轻量的 Telegram Last Name 自动更新脚本。它会通过 Telegram API 定时修改账号Last Name，让 Last Name 显示当前时间、UTC 时区偏移、日期、温度和天气状态等。

项目自带终端管理面板，安装后输入 `tg` 即可管理登录、显示项、输出顺序、更新、日志、时区同步和卸载。

> 本项目适合 Debian / Ubuntu 等使用 `systemd` 的 Linux VPS。
> 需要 Python 3.7 或更高版本。

## 🚀 功能

- 🕒 支持每 1/5/15/30/60 分钟自动更新 Telegram Last Name
- 🌍 支持显示时间、UTC 时区偏移、日期、温度、天气 Emoji
- 🎭 支持按多个时间段显示自定义 Emoji
- 🔀 支持自定义 Last Name 输出顺序
- 🧩 支持按时间段自定义完整 Last Name 规则
- 🔠 支持四种数字字体 `1 / 𝟭 / 𝟏 / 𝟙`
- 🌦️ 支持 wttr.in 天气数据
- ⚙️ 支持 systemd 后台运行和开机自启
- 🎛️ 支持终端管理面板
- 🔄 支持脚本自更新
- 📝 支持按出生日期每日自动更新 Bio
- 🧱 支持通过 `bio_templates.py` 扩展 Bio 模板
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
[8]  数字字体              切换 1 / 𝟭 / 𝟏 / 𝟙
[9]  设置地区
[10] 输出顺序              自定义 Last Name 字段顺序
[11] 一键开启全部

[12] Bio 自动更新          设置出生日期和固定 Bio
[13] Last Name 频率        设置 1/5/15/30/60 分钟
[14] Last Name 规则        切换经典/自定义模式，管理时间段规则

[15] 重启后台服务
[16] 检查并更新
[17] 同步服务器时区
[18] 强制更新 Last Name
[19] 强制更新 Bio

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
6. Emoji
```

输入新顺序即可，例如：

```text
6,3,1,2,4,5
```

对应输出顺序：

```text
Emoji > 日期 > 时间 > 时区 > 温度 > 天气
```

显示开关和输出顺序是独立的。比如关闭了温度，即使顺序里包含温度，也不会输出温度。Emoji 字段会显示当前时段命中的所有自定义 Emoji；没有命中规则时自动省略。

选择 `[8] 数字字体` 可以切换：

- `1`：普通数字
- `𝟭`：无衬线粗体数字
- `𝟏`：衬线粗体数字
- `𝟙`：双线数字

字体会应用于 Last Name 中的时间、时区、日期和温度数字，不会修改 Bio 或 Emoji。旧版 `use_bold: true/false` 配置会自动迁移为 `𝟭/1`。

## ⚙️ 配置示例

```json
{
  "show_time": true,
  "show_timezone": true,
  "show_date": false,
  "show_temp": true,
  "show_weather": true,
  "location": "Los Angeles",
  "digit_style": "sans_bold",
  "last_name_mode": "custom",
  "last_name_default_items": [
    {"type": "time"},
    {"type": "timezone"},
    {"type": "temp"},
    {"type": "weather"}
  ],
  "last_name_rules": [
    {
      "name": "Night",
      "start": "22:00",
      "end": "06:00",
      "items": [
        {"type": "text", "value": "🌙"},
        {"type": "time"}
      ]
    }
  ],
  "update_interval": 1,
  "emoji_schedules": [
    {
      "start": "09:00",
      "end": "12:00",
      "emoji": "☀️"
    },
    {
      "start": "22:00",
      "end": "06:00",
      "emoji": "🌙✨"
    }
  ],
  "name_order": [
    "time",
    "timezone",
    "date",
    "temp",
    "weather",
    "emoji"
  ]
}
```

Bio 功能配置项：

```json
{
  "bio_enabled": true,
  "birth_date": "2000-01-01",
  "fixed_bio": "Your fixed bio",
  "bio_template": "elapsed_en"
}
```

开启 `[12] Bio 自动更新` 后，脚本会使用服务器本地时区：

- 每天 03:00 将 Bio 更新为 `It lasted xx years xx months and xx days | 固定 Bio`
- Bio 更新成功后跳过下一次自动 Last Name 更新，避免同一分钟连续修改资料
- 如果服务错过 03:00 才启动，会在当天首次运行时补更新 Bio
- Fork 用户可以在 `bio_templates.py` 中新增模板函数，并注册到 `BIO_TEMPLATES`

选择 `[13] Last Name 频率` 可设置：

- `1` 分钟：每个整分钟更新
- `5` 分钟：每小时的 `00/05/10/.../55` 分更新
- `15` 分钟：每小时的 `00/15/30/45` 分更新
- `30` 分钟：每小时的 `00/30` 分更新
- `60` 分钟：每小时的 `00` 分更新

频率使用服务器本地时间对齐，不从服务启动时刻累计。手动强制更新 Last Name 不受 Bio 跳过逻辑影响。

选择 `[14] Last Name 规则` 可以切换经典/自定义模式：

- 经典模式继续使用 `[3]-[11]` 的展示开关、输出顺序和经典 Emoji 时段
- 自定义模式可以为不同时间段设置完整 Last Name 输出内容和顺序
- 可选字段包括时间、时区、日期、温度、天气、Emoji 和自定义文本
- 没有命中时间段规则时，会使用默认输出

在 `[14]` 的子菜单中仍可进入经典 Emoji 时段。经典 Emoji 时段规则：

- 每条规则包含开始时间、结束时间和一个或多个 Emoji
- 时间区间采用左闭右开，例如 `09:00-12:00` 在 09:00 生效、12:00 停止
- 支持 `22:00-06:00` 这样的跨午夜规则
- 多条规则同时命中时，Emoji 会按添加顺序合并
- Emoji 会按 `[10] 输出顺序` 中的位置显示，时段切换不受常规更新频率限制

配置文件位置：

```text
/var/lib/tg_updater/config.json
```

## 🧪 测试

在克隆的 GitHub 项目源码目录执行：

```bash
python3 -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

测试覆盖配置迁移、安装迁移、自更新依赖同步、Emoji 时段与排序、数字字体、Last Name/Bio 强制更新、天气缓存、凭证校验、Session 回滚和版本比较。

## 🔄 更新

在面板中选择 `[16] 检查并更新`。

更新流程会：

- 从 GitHub 拉取 `tg_panel.py`、`tg_daemon.py`、`bio_templates.py` 和 `requirements.txt`
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
系统账号 tg_updater
```

注意：卸载会删除 Telegram 登录 session 和本地配置。


## 📝 更新日志

### 🧩 v1.9.0

- 新增 Last Name 自定义规则模式，可按时间段配置完整输出内容和顺序
- `[14]` 升级为 Last Name 规则管理，经典 Emoji 时段保留在子菜单中
- Bio 生成拆分到 `bio_templates.py`，Fork 用户可自行扩展模板
- Bio 更新后改为跳过下一次自动 Last Name 更新，不再使用 02:00-04:00 `💤` 窗口
- 自更新和安装脚本会同步校验 `bio_templates.py`

### 🐛 v1.8.2

- 修复 root 环境重新登录时 `sudo -u` 被误处理为 `-u`，导致提示 `命令不存在: -u` 的问题
- 登录切换服务账号时优先使用 `runuser`，兼容未安装 sudo 的精简 VPS

### ✅ v1.8.1

- 修复重装时普通 sudo 用户可能误判数据目录并覆盖现有配置的问题
- 重新登录前确认服务已停止，并使用低权限服务账号生成 Session
- 登录失败或中断时自动恢复旧 Session 和原服务状态
- 服务启动时并发获取天气，天气失败后清理旧缓存并每 5 分钟重试
- 强制更新遇到 Telegram FloodWait 时保留请求并自动重试
- 固定 Telethon 依赖版本，并减少面板权限修复时的递归文件操作
- systemd unit 和快捷命令改为原子安装，降低安装中断风险
- 自更新会检查新服务运行状态，失败时自动恢复旧版本
- 自更新会同步并校验依赖声明，依赖变化时提示重新运行安装命令
- API Hash 增加 32 位十六进制格式校验，配置替换前预先设置安全所有者
- 配置保存失败不再退出面板，安装器仅在依赖安装成功后提交新代码
- 安装时校验专用系统账号，卸载时同步移除该账号
- 展示开关保存结果会停留显示，安装升级失败时自动恢复代码和 systemd unit
- 收紧 API ID 数值范围，并在 Bio 配置失败时恢复原更新状态
- 兼容未安装 sudo 的 root 精简系统，安全迁移旧版服务账号并拒绝不安全的同名用户组

### 🔧 v1.8.0

- 输出顺序新增 Emoji 字段，旧配置会自动在末尾补充
- 维护工具新增强制更新一次 Last Name
- 维护工具新增强制更新一次 Bio

### 🛡️ v1.7.1

- 收紧自更新版本号格式并限制远程文件大小
- 自更新增加核心入口校验，拒绝空文件或错误脚本
- 加强 Telegram API 环境变量和凭证格式校验
- systemd 服务明确只允许写入运行数据目录
- 修复 Emoji 状态文件缺失时旧 Emoji 可能延迟移除的问题
- 状态文件写入失败不再触发重复 Telegram 更新
- 限制配置、天气和安装下载的响应大小，降低异常数据造成的资源占用
- 修复卸载流程延迟执行和部分失败仍提示成功的问题
- API Hash 改为隐藏输入，凭证文件使用原子安全写入
- 安装模式固定运行数据目录，并拒绝符号链接安装目录，避免权限操作越界
- 收紧后台服务 capability、设备、内核接口和网络地址族权限

### 🔠 v1.7.0

- 新增四种数字字体 `1 / 𝟭 / 𝟏 / 𝟙`
- 面板 `[8]` 从粗体开关改为数字字体选择
- 旧版 `use_bold` 配置自动兼容迁移
- 一键开启全部不再覆盖用户选择的数字字体

### 🎭 v1.6.0

- 新增自定义 Last Name Emoji 时段功能
- 支持多个普通时段和跨午夜时段
- 多条规则重叠时按添加顺序合并 Emoji
- 时段开始和结束时立即更新，不受常规更新频率限制
- Emoji 状态持久化，服务重启后可正确添加或移除 Emoji

### 🛠️ v1.5.2

- 修复服务在目标分钟中途启动时未严格对齐整分边界的问题
- 修复 04:00 后重启服务时 `💤` 可能延迟恢复的问题
- 串行化 Last Name 与 Bio 更新，避免同时调用 Telegram API
- Bio 状态文件改为原子写入，降低意外中断导致文件损坏的风险
- 自动禁用超过 Telegram 长度限制的异常 Bio 配置
- 安装器改为下载并校验全部核心文件后再覆盖
- 修正手动重启服务后的更新提示

### 🕒 v1.5.1

- 新增 Last Name 更新频率设置
- 支持每 1/5/15/30/60 分钟更新
- 更新时间按服务器本地时间的整分边界对齐
- 保持 Bio 功能 02:00-04:00 的 `💤` 规则优先

### 📝 v1.5.0

- 新增每日自动更新 Bio 功能
- 支持设置出生日期和固定 Bio
- Bio 使用准确的年、月、日历日差值计算
- 开启后每天 02:00-04:00 将 Last Name 显示为 `💤`
- 每天 03:00 更新 Bio，错过执行时间时支持当天补更新，服务重启不会重复更新

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
