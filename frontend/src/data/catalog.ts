import type { MetricDefinition } from "../sdk";
// PLC寄存器来自本轮地址图片；同名氧气/气压等未确认地址保持空缺。
const plcRegisters: Record<string, number> = {
  "soil-humidity": 400,
  "soil-temp": 402,
  "soil-ec": 404,
  "soil-ph": 406,
  "soil-n": 408,
  "soil-p": 410,
  "soil-k": 412,
  uv: 414,
  "uv-index": 416,
  "inside-humidity-04": 430,
  "inside-temp-04": 432,
  co2: 434,
  light: 436,
  "outside-humidity": 440,
  "outside-temp": 442,
  "inside-humidity-06": 450,
  "inside-temp-06": 452,
  co: 460,
};
// 只含定义、不含读数；地址06与04的温湿度保留独立来源。
export const metricCatalog: MetricDefinition[] = [
  ["co", "一氧化碳", "空气质量", "地址01"],
  ["uv", "紫外线", "空气质量", "地址02"],
  ["oxygen", "氧气", "空气质量", "地址03"],
  ["co2", "二氧化碳", "棚内", "地址04 · 四合一"],
  ["light", "光照", "棚内", "地址04 · 四合一"],
  ["inside-temp-04", "空气温度", "棚内", "地址04 · 四合一"],
  ["inside-humidity-04", "空气湿度", "棚内", "地址04 · 四合一"],
  ["outside-pressure", "棚外气压", "棚外", "地址05"],
  ["outside-temp", "棚外温度", "棚外", "地址05"],
  ["outside-humidity", "棚外湿度", "棚外", "地址05"],
  ["inside-pressure", "棚内气压", "棚内", "地址06"],
  ["inside-temp-06", "空气温度", "棚内", "地址06 · 温湿压"],
  ["inside-humidity-06", "空气湿度", "棚内", "地址06 · 温湿压"],
  ["soil-temp", "土壤温度", "土壤", "土壤七合一"],
  ["soil-humidity", "土壤湿度", "土壤", "土壤七合一"],
  ["soil-ph", "土壤 pH", "土壤", "土壤七合一"],
  ["soil-ec", "土壤电导率", "土壤", "土壤七合一"],
  ["soil-n", "土壤氮", "土壤", "土壤七合一"],
  ["soil-p", "土壤磷", "土壤", "土壤七合一"],
  ["soil-k", "土壤钾", "土壤", "土壤七合一"],
  ["uv-index", "紫外线指数", "空气质量", "地址02"],
].map(([id, name, group, source], order) => ({
  id,
  siteId: "default-site",
  name,
  group,
  source:
    plcRegisters[id] === undefined
      ? source
      : `${source} · PLC D${plcRegisters[id]}`,
  unit: null,
  order,
  enabled: true,
}));
export const actuatorCatalog = [
  "散热风扇",
  "加热器",
  "补光灯",
  "喷雾水泵",
  "施肥水泵",
  "滴灌水泵",
  "棉被电机",
  "卷帘电机",
];
