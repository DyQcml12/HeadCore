import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputDir] = process.argv.slice(2);
if (!inputPath || !outputDir) {
  throw new Error("usage: node build_head_planning_blind_review.mjs <input.json> <output-dir>");
}

const items = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();
const instructions = workbook.worksheets.add("Instructions");
const form = workbook.worksheets.add("Review Form");
instructions.showGridLines = false;
form.showGridLines = false;

instructions.getRange("A1:F1").merge();
instructions.getRange("A1").values = [["HeadCore 规划外部盲评"]];
instructions.getRange("A1:F1").format = {
  fill: "#8B1E2D",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  rowHeight: 34,
  verticalAlignment: "center",
};
instructions.getRange("A3:B8").values = [
  ["目的", "针对同一条用户消息，比较两种匿名回应策略。"],
  ["评审者 ID", "每一行填写同一个非空匿名 ID，不要填写真实姓名。"],
  ["选择", "在 selected_option 列选择 A 或 B。"],
  ["信心", "可选，填写 1（最低）到 5（最高）的整数。"],
  ["备注", "可选，简要记录选择该方案的主要原因。"],
  ["盲评边界", "本工作簿不包含 HeadCore 的选择、动作枚举、评分或答案键。"],
];
instructions.getRange("A3:A8").format = { fill: "#F4E7E9", font: { bold: true, color: "#5D1520" } };
instructions.getRange("A3:B8").format.wrapText = true;
instructions.getRange("A:A").format.columnWidth = 20;
instructions.getRange("B:B").format.columnWidth = 78;
instructions.getRange("3:8").format.rowHeight = 36;

const headers = [
  "reviewer_id", "item_id", "scenario_id", "user_input", "option_a", "option_b",
  "selected_option", "confidence", "notes",
];
const rows = items.map((item) => [
  "", item.item_id, item.scenario_id, item.user_input, item.option_a, item.option_b, "", "", "",
]);
form.getRange(`A1:I${rows.length + 1}`).values = [headers, ...rows];
form.getRange("A1:I1").format = {
  fill: "#333333",
  font: { bold: true, color: "#FFFFFF" },
  rowHeight: 28,
  horizontalAlignment: "center",
};
form.getRange(`A2:I${rows.length + 1}`).format = {
  verticalAlignment: "top",
  wrapText: true,
};
form.getRange(`A2:A${rows.length + 1}`).format.fill = "#FFF3CD";
form.getRange(`G2:I${rows.length + 1}`).format.fill = "#FFF3CD";
form.getRange(`G2:G${rows.length + 1}`).dataValidation = {
  rule: { type: "list", formula1: '"A,B"' },
};
form.getRange(`H2:H${rows.length + 1}`).dataValidation = {
  rule: { type: "wholeNumber", operator: "between", formula1: 1, formula2: 5 },
};
form.getRange("A:A").format.columnWidth = 18;
form.getRange("B:B").format.columnWidth = 17;
form.getRange("C:C").format.columnWidth = 23;
form.getRange("D:D").format.columnWidth = 42;
form.getRange("E:F").format.columnWidth = 40;
form.getRange("G:G").format.columnWidth = 18;
form.getRange("H:H").format.columnWidth = 13;
form.getRange("I:I").format.columnWidth = 35;
form.getRange(`2:${rows.length + 1}`).format.rowHeight = 64;
form.freezePanes.freezeRows(1);
form.freezePanes.freezeColumns(3);

await fs.mkdir(outputDir, { recursive: true });
const inspect = await workbook.inspect({ kind: "sheet,region", range: "A1:I12", maxChars: 5000 });
await fs.writeFile(path.join(outputDir, "workbook-inspection.txt"), inspect.ndjson ?? String(inspect), "utf8");
for (const sheetName of ["Instructions", "Review Form"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, `${sheetName.toLowerCase().replace(" ", "-")}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "HEADCORE_PLANNING_BLIND_REVIEW_PACKAGE_2026-07-22.xlsx"));
