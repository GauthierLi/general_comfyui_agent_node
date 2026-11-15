# 工具节点

## 逻辑控件（Easy-Use 移植）

本组节点移植自 `ComfyUI-Easy-Use` 的 `py/nodes/logic.py`（commit `595e073`）。
共 47 个逻辑节点，分类统一为“工具”。
节点 ID 和显示名都不带 `easy` 前缀，例如节点 ID `compare`、显示名“Compare”。
使用旧 ID（`easy compare` 等）保存的工作流无法加载这些节点，用户必须重新添加。
节点算法和展开逻辑原样保留，仅把 V1 节点外壳适配为 V3。

包含的节点组：

| 节点组 | 节点 |
| --- | --- |
| 类型 | String、Int、Range(Int)、Float、Range(Float)、Boolean |
| 数学 | Math String、Math Int、Math Float、Simple Math、Simple Math Dual、Compare |
| 开关 | Image Switch、Text Switch、A or B、Any Inversed Switch |
| 索引开关 | Any/Image/Text/Conditioning Index Switch |
| 循环 | While Loop Start/End、For Loop Start/End |
| 分支 | If else、Blocker |
| 判断 | Is Mask Empty、Is None、Is SDXL、Is File Exist |
| 转换 | String to Int List、String to Float List、String Join Lines、Output to List、Convert Any |
| 数组 | XY Any、Length Any、Index Any、Batch Any |
| 输出 | Pixels W/H Norm、Show Any、Show Tensor Shape |
| 工具 | Clear Cache Key、Clear Cache All、Clean VRAM Used、Save Text、Sleep |

### 循环用法（While / For）

While 需要一对节点：“While Loop Start”标记循环体起点，“While Loop End”检查条件。

| 方向 | 插口 | 含义 |
| --- | --- | --- |
| Start 输入 | condition | 布尔控件，默认 `true`。设为 `false` 时跳过整个循环。 |
| Start 输入 | value0～value19 | 第一轮的初始值。 |
| Start 输出 | flow | 控制流，接到 End 的 flow。 |
| Start 输出 | value0～value19 | 本轮初始值，供循环体使用。 |
| End 输入 | flow | 控制流，来自 Start 的 flow。 |
| End 输入 | condition | 循环体每轮返回的 `BOOLEAN` 判断。 |
| End 输入 | value0～value19 | 循环体产生的新值，供下一轮使用。 |
| End 输出 | value0～value19 | 循环结束后的最终值，供循环外节点使用。 |

连线步骤：

1. 用户将 Start 的 `flow` 接到 End 的 `flow`。
2. 用户将 Start 的 `value0`～`value19` 接到循环体入口。
3. 用户将循环体结果接到 End 的 `value0`～`value19`。
4. 用户将循环体的 `BOOLEAN` 判断接到 End 的 `condition`。
5. 用户将 End 的 `value0`～`value19` 接到循环外节点。

循环流程：

1. Start 的 `condition` 为 `false` 时，整个循环被跳过。
2. 否则执行一轮循环体。
3. End 检查 `condition`。为 `true` 时重复循环体，为 `false` 时输出结果。

For 循环使用 `For Loop Start` 与 `For Loop End` 一对节点。
Start 的 `total` 指定循环次数，`index` 从 `initial_value0`（默认 0）开始递增。
For 节点内部复用 While 循环实现。

边界：

- 循环体不能包含另一个 While Loop End 或 For Loop End。
- 循环体内可以包含输出节点；输出节点每轮都会执行。
- 后端每轮最多 20 个值通道（`value0`～`value19`）。
- 前端脚本 `js/logic_flow.js` 默认只显示 2 个值通道。For 节点的 `index` 不计入这 2 个。
  用户连接最后一个值通道后，节点追加下一个通道，最多 20 个。
  用户断开末尾的连线后，节点删除末尾未连接的通道，并保留 2 个默认通道。
  节点库预览也只显示默认通道。
- 循环节点不提供最大轮次保护。用户必须保证 `condition` 最终变为 `false`，
  否则任务会一直循环。用户可点击 ComfyUI 的停止按钮中断。

## 判断（ICafeCompare）

1. 用户在“工具”分类添加“判断”节点。
2. 用户选择“类型”：`int`（默认）、`float` 或 `str`。
3. 用户填写“左操作数”，选择“运算符”，再填写“右操作数”。
4. 用户将 `BOOLEAN` 类型的“判断结果”连接到下游节点。

节点计算 `左操作数 运算符 右操作数`。运算符默认为 `==`。
数字支持 `>`、`>=`、`<`、`<=`、`==`、`!=`。
字符串只支持 `==`、`!=`，区分大小写并保留全部空白。
节点按类型显示原生整数、浮点数或字符串控件，也支持对应类型的连线。
后端拒绝非法运算符、布尔值及隐式字符串转换。

整数控件范围为 `[-9007199254740991, 9007199254740991]`，避免浏览器整数精度丢失。
后端不截断连线传入的大整数。`float` 接受整数或浮点数，遵循 Python 数值比较语义。
浮点数相等判断不使用误差容限。NaN 和无穷值遵循 Python 比较语义。
节点需要支持 V3 `DynamicCombo` 的 ComfyUI 和前端，无额外依赖或前端脚本。

## pop（ICafePop）

“pop”节点取出列表的第一个元素。

- 输入“列表”接受两种来源：
  - ComfyUI 输出列表，例如“文本展示”的 `text` 输出。
  - 单个 Python 列表值，例如 “String to Int List”的输出，或循环节点的 `value` 通道。
- 输出“第一个元素”是列表的第一个元素。
- 输出“剩余列表”是去掉第一个元素后的 Python 列表，可以直接连回循环 End 的 `initial_value`。
- 如果输入列表为空，则节点报错。用户应先用“Length Any”判断长度。
- 如果 ComfyUI 输出列表只有一个元素且该元素本身是列表，则节点把该元素当作输入列表。

逐个处理列表的 While 连法：列表 → Start `initial_value0`，Start `value0` → pop。
pop“剩余列表”同时连到 End `initial_value0` 和“Length Any”。
“Compare”（`a > b`，`b` 为 0）的结果连到 End `condition`。

## accumulate（ICafeAccumulate）

“accumulate”节点把“元素”追加到“已有列表”末尾，输出新的 Python 列表“列表”。

- 输入“元素”接受任意类型。如果上游是 ComfyUI 输出列表，则节点追加全部元素。
- 输入“已有列表”可选。如果未连接或值为 `None`，则节点从空列表开始。
- 如果“元素”本身是 Python 列表，则节点把它作为一个元素追加，不展开。

在 While 中收集每轮结果：Start `value1` → “已有列表”，循环体结果 → “元素”。
accumulate“列表”连到 End `initial_value1`。Start `initial_value1` 保持未连接。
循环结束后，End `value1` 输出全部结果组成的列表。

## list_string_transfer（ICafeListStringTransfer）

“list_string_transfer”节点在列表和字符串之间转换。选项“分隔符”只支持换行、逗号、空格。

- 如果输入是列表，则节点用分隔符拼接全部元素，输出一个字符串。非字符串元素先转为 `str`。
  - 列表可以是 ComfyUI 输出列表，例如 `case_ids`，也可以是单个 Python 列表值，例如 accumulate 的输出。
- 如果输入是单个字符串，则节点按分隔符切分，去掉每项首尾空白和空项，输出单个 Python 列表值。
- 如果 ComfyUI 输出列表只有一个字符串元素，则节点按字符串切分。

`case_ids` → list_string_transfer → Agent `context_1`，可以让 Agent 只运行一次并收到全部 ID。

## image_path_preview（ICafeImagePathPreview）

“image_path_preview”节点按“图像路径”读取图片，并在节点上预览。节点没有输出。

- 路径可以手填，也可以连接上游的字符串、ComfyUI 输出列表或单个 Python 列表值。输入多个路径时，节点预览全部图片。
- 节点接受任意绝对路径，读取权限与 ComfyUI 进程相同。`~` 会展开为用户主目录。
- 节点把图片转为 RGB，按 EXIF 方向旋转，再存入 ComfyUI 临时目录供浏览器显示。原文件不修改。
- 如果路径为空或文件不存在，则节点报错。

## 测试

用户在项目根目录使用已安装 ComfyUI 依赖的 Python 3.12 环境运行：

```bash
PYTHONPATH=ComfyUI python3.12 -m unittest discover -s custom_nodes/tool_nodes -p 'test_*.py' -v
node custom_nodes/tool_nodes/test_custom_parameters.cjs
node custom_nodes/tool_nodes/test_logic_flow.cjs
```

逻辑控件与循环测试调用真实 `PromptExecutor`，使用 CPU，不提交 DataServer 请求。
