# HD1910 7.4 V M6 参数来源

`feetech_hd1910_7_4V_m6.json` 按原始字节保存飞特公开参数，不是本项目实机标定。

- 项目：[ftservo/ftservo-bam](https://github.com/ftservo/ftservo-bam)
- 固定版本：`4f7c0b0de3debf9c1ab254fc9654676e8aab9317`
- 上游文件：[bam/params/feetech_hd1910_7_4V/m6.json](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/params/feetech_hd1910_7_4V/m6.json)
- SHA256：`81a441fb921130bcc9bcfbd9ee0c77e3c38d9ab758bc7e0559fb029c436355ba`
- 许可：Apache-2.0，见同级执行器目录的 `THIRD_PARTY_LICENSE` 和 `NOTICE`。

JSON 中 `actuator="hd1910"` 与厂家注册表的 `HD1910` 大小写不一致。本项目加载器明确接受这两个别名，不依赖上游注册表，也不修改原始 JSON。

`kt`、`R`、`armature` 和摩擦系数是厂家辨识得到的模型参数，不应当作本项目实测值或独立电机规格。
`q_offset` 是辨识装置零位偏差，`command_delay` 是辨识工况延迟；本项目保留这两个数值作为来源记录，不将其用作机器人的关节零位或总线延迟。

厂家 HD1910 控制器模型默认供电 7.4 V、固件 P 增益 32、误差转换系数 0.163、最大 PWM 占空比 0.97。
这些常量来自 `bam/feetech/actuator.py`，而不是 JSON 中的字段。此模型不包含独立固件 D 项，是否符合实机当前固件、控制模式和增益，仍需通过实际响应确认。

首次验证应保持固定电压、摩擦系数为 1、无额外命令延迟，再与单关节响应比较。随机化范围应来自测量或明确标记的仿真假设。

本项目摩擦计算遵循同版本 `bam/model.py` 中用于辨识的标量 M6 公式：二次项仅在电机和外载荷力矩符号不同且绝对值不等时启用。
厂家该版本 `bam/mjlab.py` 的向量化实现遗漏符号条件，并在绝对值相等时选用反驱分支；本项目将这两处按标量辨识模型修正。
