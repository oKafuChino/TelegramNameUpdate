# ✨ Telegram Name Updater (动态名字更新面板)

一个轻量、优雅且高度自动化的 Telegram 姓氏（Last Name）动态更新工具。
不仅能让你的名字实时显示**时间、日期、当地温度与天气状态**，还附带了一个极客风的**终端交互面板 (TUI)**，让你在服务器上可以像使用普通软件一样轻松管理它。

完美兼容原生 Debian 13 / Ubuntu 等启用了 PEP 668 环境隔离保护的现代 Linux 系统。

## 🌟 功能特性

- **🕒 实时同步**：每分钟精确跳动，支持显示当前时间与日期。
- **⛅ 天气联动**：自动拉取指定城市的实时温度，并匹配对应的天气 Emoji（如 ☀️、🌧️、❄️）。
- **🔠 粗体美化**：自动将时间与温度的普通数字转换为 Unicode 无衬线粗体（如 `𝟭𝟰:𝟯𝟬 𝟮𝟱°C ☀️`），视觉效果更佳。
- **🖥️ 交互面板**：无需修改代码，终端输入 `tg` 即可唤出可视化管理面板，0-11 选项一键开关各项功能。
- **🛡️ 纯净隔离**：全自动配置 Python `venv` 虚拟环境，不污染宿主机系统环境。
- **⚙️ 守护进程**：使用 `systemd` 托管，后台静默运行，支持开机自启与崩溃自动重启。
- **🔄 无损热更新**：面板自带版本检测机制，按一个键即可从 GitHub 拉取最新代码并自动重启，不丢失任何个性化配置。

---

## 🚀 一键安装 (推荐)

在支持 `systemd` 的 Debian / Ubuntu 系统终端中，以 `root` 或 `sudo` 权限直接运行以下命令即可完成自动部署：

```bash
bash <(curl -sL [https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main/install.sh](https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main/install.sh))