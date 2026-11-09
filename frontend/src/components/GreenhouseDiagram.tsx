import { useState } from "react";
import { useMonitoring } from "./MonitoringPanels";
import { displayDate } from "../lib/format";
export function GreenhouseDiagram() {
  const m = useMonitoring();
  const [selected, setSelected] = useState("fan");
  const nodes = [
    { id: "fan", name: "散热风扇", x: 460, y: 181 },
    { id: "light", name: "补光灯", x: 360, y: 239 },
    { id: "heater", name: "加热器", x: 236, y: 358 },
    { id: "mist-pump", name: "喷雾水泵", x: 136, y: 394 },
    { id: "drip-pump", name: "滴灌水泵", x: 194, y: 422 },
    { id: "fertilizer-pump", name: "施肥水泵", x: 253, y: 448 },
    { id: "blanket-forward", name: "棉被电机", x: 390, y: 112 },
    { id: "curtain-forward", name: "卷帘电机", x: 515, y: 319 },
  ];
  const output = m?.outputs.find((o) => o.id === selected);
  const fault = m?.faults.find((f) => f.id === selected);
  const color = (id: string) =>
    m?.faults.find((f) => f.id === id)?.state === "fault"
      ? "#f27b79"
      : m?.outputs.find((o) => o.id === id)?.state === true
        ? "#65cdb3"
        : "#7893b5";
  return (
    <div className="equipment-diagram">
      <svg
        viewBox="0 0 700 520"
        role="img"
        aria-label="实体大棚与八类执行机构的分区示意，可选择设备查看输出状态"
      >
        <defs>
          <pattern
            id="floorGrid"
            width="34"
            height="18"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M0 0H34V18"
              fill="none"
              stroke="#254469"
              strokeWidth=".5"
            />
          </pattern>
        </defs>
        <path
          d="M43 357 289 487 667 280 426 156Z"
          fill="#0b1b31"
          stroke="#345477"
        />
        <path
          d="M43 357 289 487V504L43 374ZM289 487 667 280V297L289 504Z"
          fill="#0e2946"
          stroke="#345477"
        />
        <path d="M63 352 290 472 645 280 423 174Z" fill="url(#floorGrid)" />
        <g stroke="#4a739d" strokeWidth="1.8" fill="#245077" fillOpacity=".12">
          <path d="M199 326V198L301 78 531 193V320L430 442V314L199 198Z" />
          <path d="M301 78V205L531 320M199 326 430 442M301 205 430 314M430 314 531 193" />
          {[1, 2, 3, 4].map((i) => (
            <g key={i}>
              <path
                d={`M${199 + i * 46} ${198 + i * 23}V${326 + i * 23}M${301 + i * 46} ${78 + i * 23}V${205 + i * 23}M${199 + i * 46} ${198 + i * 23} ${301 + i * 46} ${78 + i * 23}`}
              />
            </g>
          ))}
          <path
            d="M199 262 430 378 531 257M301 142 531 257"
            strokeDasharray="4 5"
          />
        </g>
        <path
          d="M202 196 301 79 531 193 491 242 261 127Z"
          fill="#4c9fd1"
          opacity=".2"
          stroke="#8fb9df"
        />
        <g fill="#183650" stroke="#6188ad">
          <path d="M351 296 422 332 462 309 390 273Z" />
          <path d="M277 327 348 363 388 340 316 304Z" />
          <path d="M351 296V310L422 347V332M277 327V341L348 377V363" />
        </g>
        <g fill="none" stroke="#4faaa5" strokeWidth="3">
          <path d="M143 397 302 317 400 366M197 425 329 356M256 451 375 389" />
          <path
            d="M264 293 421 372M285 283 440 361"
            strokeWidth="1.5"
            strokeDasharray="4 4"
          />
        </g>
        <g stroke="#617f9e" fill="#16324e">
          <path d="M96 329V230L154 200 170 207" strokeWidth="5" fill="none" />
          <ellipse cx="174" cy="208" rx="14" ry="9" />
          <path d="M163 208V226Q176 240 186 225V208" />
          <path d="M106 364V284L156 309V390Z" />
          <path d="M113 308 148 326M113 319 148 337M113 330 148 348" />
        </g>
        <g fill="#51769a" fontSize="11">
          <text x="70" y="270">
            现场视频
          </text>
          <text x="88" y="407">
            独立水路
          </text>
          <text x="545" y="245">
            棚内感知区
          </text>
        </g>
        {nodes.map((n) => (
          <g
            key={n.id}
            role="button"
            tabIndex={0}
            aria-label={`查看${n.name}`}
            onClick={() => setSelected(n.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSelected(n.id);
              }
            }}
            className="diagram-node"
          >
            <circle
              cx={n.x}
              cy={n.y}
              r={selected === n.id ? 15 : 10}
              fill="#0d223b"
              stroke={color(n.id)}
              strokeWidth="2"
            />
            <circle cx={n.x} cy={n.y} r="3" fill={color(n.id)} />
            <text
              x={n.x + 18}
              y={n.y + 4}
              fill={selected === n.id ? "#edf4ff" : "#91a9c5"}
              fontSize="12"
            >
              {n.name}
            </text>
          </g>
        ))}
        <g fill="#607f9e" fontSize="10">
          <text x="405" y="478">
            装备分区示意 · 非精确定位
          </text>
        </g>
      </svg>
      <div className="diagram-selection">
        <span>
          <i style={{ background: color(selected) }} />
          {nodes.find((n) => n.id === selected)?.name}
        </span>
        <b>
          {fault?.state === "fault"
            ? "设备故障"
            : output?.state === true
              ? "PLC输出开启"
              : output?.state === false
                ? "PLC输出关闭"
                : "输出未知"}
        </b>
        <small>
          {output?.receivedAt ? displayDate(output.receivedAt) : "等待现场回读"}
        </small>
      </div>
    </div>
  );
}
