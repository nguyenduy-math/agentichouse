import re

import llm_client
from models import Step, Plan

PLANNER_SYSTEM = """Bạn là một agent lập kế hoạch. Cho một nhiệm vụ, hãy xuất ra kế hoạch từng bước
sử dụng các công cụ có sẵn. Dùng #E1, #E2, ... để đặt tên cho các biến bằng chứng.
Tham chiếu các biến trước đó bằng tên trong các bước sau.

Các công cụ có sẵn:
- search(query)                          — tìm kiếm web, trả về đoạn văn bản
- summarize_top3(results1, results2)     — LLM: chọn 3 tin tức AI nổi bật từ hai nguồn
- draft_email(briefing, language)        — LLM: soạn email chuyên nghiệp

Định dạng đầu ra (bắt buộc):
Plan:
#E1 = tên_công_cụ[đối_số1, đối_số2, ...]
#E2 = tên_công_cụ[đối_số1, ...]
...

Quy tắc:
- Dùng tham chiếu #En để truyền kết quả giữa các bước
- Các bước độc lập (không có phụ thuộc chung) có thể liệt kê theo bất kỳ thứ tự nào — worker sẽ chạy song song
- Không giải thích, chỉ xuất khối Plan"""

PLANNER_USER = "Nhiệm vụ: {query}"

STEP_PATTERN = re.compile(r"(#E\d+)\s*=\s*(\w+)\[([^\]]*)\]")


def parse_plan(plan_text: str) -> Plan:
    """Parse LLM plan output into a Plan object."""
    steps = []
    for match in STEP_PATTERN.finditer(plan_text):
        var, tool, raw_args = match.groups()
        args = [a.strip().strip("\"'") for a in raw_args.split(",") if a.strip()]
        steps.append(Step(var=var, tool=tool, args=args))
    return Plan(steps=steps)


def build_dependency_graph(plan: Plan) -> dict[str, set[str]]:
    """Returns {var: set of vars it depends on}."""
    deps: dict[str, set[str]] = {}
    for step in plan.steps:
        step_deps: set[str] = set()
        for arg in step.args:
            if re.match(r"#E\d+", arg):
                step_deps.add(arg)
        deps[step.var] = step_deps
    return deps


def generate_plan(query: str) -> Plan:
    """Call the LLM to generate a ReWOO plan for the given query."""
    plan_text = llm_client.chat_completion(
        system=PLANNER_SYSTEM,
        user=PLANNER_USER.format(query=query),
        max_tokens=512,
    )
    return parse_plan(plan_text)
