#!/usr/bin/env python3
"""
Інтерактивна візуалізація залежностей execution_position (+ shadow).
"""

import json
from pathlib import Path
from typing import Dict, List


class HTMLReportGenerator:
    """Генератор HTML звітів."""

    @staticmethod
    def generate_interactive_report(
        json_data: Dict,
        output_file: str = "dependency_report.html"
    ):
        """Генерація інтерактивного HTML звіту."""

        modules = json_data['modules']
        exports = json_data['exports']
        unused = json_data['unused_exports']
        deps = json_data['internal_dependencies']
        cycles = json_data['cycles']

        total_exports = sum(len(e) for e in exports.values())
        total_unused = sum(len(u) for u in unused.values())

        nodes_data = json.dumps([{'id': m} for m in modules])
        links_data = json.dumps([{'source': src, 'target': dst}
                                for src, dst_set in deps.items() for dst in dst_set])

        html_content = f"""<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Аналіз залежностей: execution_position (+ shadow)</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: white;
                     border-radius: 12px; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                     overflow: hidden; }}
        header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                 color: white; padding: 40px 30px; text-align: center; }}
        header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                   gap: 20px; padding: 30px; background: #f8f9fa; }}
        .metric-card {{ background: white; padding: 20px; border-radius: 8px;
                       border-left: 4px solid #667eea; }}
        .metric-card h3 {{ color: #667eea; font-size: 0.9em; text-transform: uppercase;
                          margin-bottom: 10px; }}
        .metric-card .value {{ font-size: 2em; font-weight: bold; color: #333; }}
        .sections {{ padding: 30px; }}
        .section {{ margin-bottom: 40px; }}
        .section h2 {{ color: #667eea; font-size: 1.8em; margin-bottom: 20px;
                      padding-bottom: 10px; border-bottom: 2px solid #667eea; }}
        .graph-container {{ background: #f8f9fa; border-radius: 8px; padding: 20px;
                           margin-top: 20px; min-height: 500px; }}
        .module-list {{ display: grid; gap: 10px; }}
        .module-item {{ background: #f8f9fa; padding: 15px; border-radius: 6px;
                       border-left: 3px solid #667eea; }}
        footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #666;
                 border-top: 1px solid #dee2e6; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Аналіз залежностей</h1>
            <p>execution_position + shadow_execpos</p>
        </header>

        <div class="metrics">
            <div class="metric-card">
                <h3>📁 Модулів</h3>
                <div class="value">{len(modules)}</div>
            </div>
            <div class="metric-card">
                <h3>📤 Експортів</h3>
                <div class="value">{total_exports}</div>
            </div>
            <div class="metric-card">
                <h3>⚠️  Невикористовуваних</h3>
                <div class="value">{total_unused}</div>
            </div>
            <div class="metric-card">
                <h3>🔄 Циклів</h3>
                <div class="value">{len(cycles)}</div>
            </div>
        </div>

        <div class="sections">
            <div class="section">
                <h2>📋 Модулі ({len(modules)})</h2>
                <div class="module-list">
                    {HTMLReportGenerator._generate_module_list(modules, deps, cycles, exports)}
                </div>
            </div>

            {HTMLReportGenerator._generate_unused_section(unused)}
            {HTMLReportGenerator._generate_cycles_section(cycles)}

            <div class="section">
                <h2>🔗 Граф залежностей</h2>
                <div class="graph-container" id="graph"></div>
            </div>
        </div>

        <footer>
            <p>Генеровано автоматично</p>
        </footer>
    </div>

    <script>
        const nodes = {nodes_data};
        const links = {links_data};

        const width = 900, height = 500;
        const svg = d3.select("#graph").append("svg").attr("width", width).attr("height", height);

        const simulation = d3.forceSimulation(nodes)
            .force("link", d3.forceLink(links).id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-300))
            .force("center", d3.forceCenter(width / 2, height / 2));

        const link = svg.append("g").selectAll("line")
            .data(links).enter().append("line")
            .attr("stroke", "#999").attr("stroke-opacity", 0.6);

        const node = svg.append("g").selectAll("circle")
            .data(nodes).enter().append("circle")
            .attr("r", 8).attr("fill", "#667eea").attr("stroke", "white").attr("stroke-width", 2);

        node.append("title").text(d => d.id);

        simulation.on("tick", () => {{
            link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
            node.attr("cx", d => d.x).attr("cy", d => d.y);
        }});
    </script>
</body>
</html>
"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✅ HTML звіт створений: {output_file}")

    @staticmethod
    def _generate_module_list(modules: List[str], deps: Dict[str, set],
                              cycles: List[List[str]], exports: Dict[str, set]) -> str:
        """Генерація списку модулів."""
        html = []

        for module in sorted(modules):
            fan_in = sum(1 for deps_set in deps.values() if module in deps_set)
            fan_out = len(deps.get(module, set()))
            in_cycle = any(module in cycle for cycle in cycles)

            html.append(f'<div class="module-item">')
            html.append(f'  <strong>{module}</strong>')
            html.append(
                f'  <div>Експортує: {len(exports.get(module, []))} символів, Fan-In: {fan_in}, Fan-Out: {fan_out}</div>')

            if in_cycle:
                html.append(
                    f'  <span style="color:red;">⚠️  Циклічна залежність</span>')

            html.append(f'</div>')

        return "\n".join(html)

    @staticmethod
    def _generate_unused_section(unused: Dict[str, set]) -> str:
        """Генерація секції невикористовуваних."""
        if not unused:
            return '<div class="section"><h2>✅ Невикористовувані експорти</h2><p>Не знайдено</p></div>'

        html = ['<div class="section">',
                '<h2>⚠️  Потенційно невикористовувані експорти</h2>']

        for module, exports in sorted(unused.items()):
            html.append(
                f'<div><strong>{module}</strong>: {", ".join(sorted(exports))}</div>')

        html.append('</div>')
        return "\n".join(html)

    @staticmethod
    def _generate_cycles_section(cycles: List[List[str]]) -> str:
        """Генерація секції циклів."""
        if not cycles:
            return '<div class="section"><h2>✅ Циклічні залежності</h2><p>Не знайдено</p></div>'

        html = ['<div class="section">', '<h2>🔄 Циклічні залежності</h2>']

        for cycle in cycles:
            html.append(
                f'<div><strong>Цикл:</strong> {" → ".join(cycle)}</div>')

        html.append('</div>')
        return "\n".join(html)


def main():
    """Головна функція."""
    exec_pos_dir = Path(__file__).parent.parent / "apps" / \
        "reference" / "domains" / "execution_position"
    output_dir = exec_pos_dir / "analysis_output"

    json_file = output_dir / "dependencies.json"

    if not json_file.exists():
        print("⚠️  Спочатку запустіть analyze_execution_position_deps.py")
        return

    with open(json_file, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    HTMLReportGenerator.generate_interactive_report(
        json_data,
        str(output_dir / "dependency_report.html")
    )

    print(
        f"\n🎉 Звіт готовий! Відкрийте: {output_dir / 'dependency_report.html'}")


if __name__ == "__main__":
    main()
