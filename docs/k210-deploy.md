# K210 部署入口

当前部署契约、固件、SD 一键安装、串口问题和实测边界统一记录在
[环境与部署说明](environment-and-deployment.md)。

最重要的几条：

- 默认模型：160×120，2,089,896 字节，
  `060163f63db6b4bb818a3c8483ca2f686f3e7e1331bef09b7567b79422fc3b6a`；
- 默认模式：`SMOKE`；
- 固件：已实测 MaixPy 0.6.2；
- 安装器不格式化 SD、不刷固件；
- IDE 观察 FPS 不是正式 benchmark；
- e20 是未物理复验候选，不进入默认 SD 包。
