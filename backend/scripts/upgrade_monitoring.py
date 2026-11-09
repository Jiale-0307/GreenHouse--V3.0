"""显式升级已有读取配置；只改指定本地JSON，绝不连接设备或修改PLC/DTU。"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.modbus_mqtt import ModbusMqttConfig


def upgrade(data):
    points = list(data["points"])
    additions = []
    for metric, address in [("oxygen", 420), ("outside-pressure", 444), ("inside-pressure", 454)]:
        additions.append(
            dict(
                metricId=metric,
                address=address,
                slaveId=1,
                kind="mean",
                dataType="float_word_swap",
                enabled=True,
                mappingConfirmed=False,
            )
        )
    for metric, address, kind in [
        ("mode", 900, "mode"),
        ("outputs", 600, "outputs"),
        ("meter", 270, "meter"),
    ]:
        additions.append(
            dict(metricId=metric, address=address, slaveId=1, kind=kind, dataType="uint16", enabled=True)
        )
    additions.extend(
        dict(
            metricId=f"fault-{address}",
            address=address,
            slaveId=1,
            kind="fault",
            dataType="uint16",
            enabled=True,
        )
        for address in range(1000, 2701, 100)
    )
    for addition in additions:
        previous = next((p for p in points if p["metricId"] == addition["metricId"]), None)
        if previous is None:
            points.append(addition)
        elif addition["kind"] == "mean" and not previous.get("enabled", False):
            points[points.index(previous)] = addition
        elif addition["kind"] == "mean" and previous.get("kind", "metric") != "mean":
            raise ValueError(f"已有启用的{addition['metricId']}配置，请先人工核对来源、倍率与范围")
    result = {**data, "points": points}
    ModbusMqttConfig.model_validate(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True, help="新文件，禁止覆盖输入或现有配置")
    args = parser.parse_args()
    result = upgrade(json.loads(Path(args.input).read_text()))
    with Path(args.output).open("x") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("只读监测配置已生成；均值/电表物理量发布保持待确认，未连接网络。")
