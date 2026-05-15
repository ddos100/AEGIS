import { useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3-force';
import { select } from 'd3-selection';
import { zoom, zoomIdentity, type ZoomBehavior } from 'd3-zoom';
import { Link } from 'react-router-dom';
import { useEcosystemMap } from '@/hooks/useCompliance';
import type { EcosystemEdge, EcosystemNode } from '@/types/compliance';

const RISK_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#eab308',
  low:      '#22c55e',
};
const SHADOW_COLOR = '#6366f1';

type SimNode = EcosystemNode & d3.SimulationNodeDatum;
type SimLink = d3.SimulationLinkDatum<SimNode> & EcosystemEdge;

export default function EcosystemMap({ height = 520 }: { height?: number }) {
  const { data, isLoading } = useEcosystemMap();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [selected, setSelected] = useState<SimNode | null>(null);
  const [query, setQuery] = useState('');

  const nodes = useMemo<SimNode[]>(
    () => (data?.nodes ?? []).map((n) => ({ ...n })),
    [data],
  );
  const links = useMemo<SimLink[]>(
    () => (data?.edges ?? []).map((e) => ({ ...e })),
    [data],
  );

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;
    const svg = select(svgRef.current);
    const width = svgRef.current.clientWidth;
    svg.selectAll('*').remove();

    const container = svg.append('g').attr('class', 'aegis-zoom');

    // Edges
    const link = container.append('g')
      .attr('stroke', '#cbd5e1').attr('stroke-opacity', 0.5).attr('stroke-width', 1)
      .selectAll('line').data(links).enter().append('line');

    // Nodes
    const node = container.append('g')
      .selectAll<SVGCircleElement, SimNode>('circle')
      .data(nodes)
      .enter().append('circle')
      .attr('r', (d) => Math.max(6, Math.min(28, 6 + Math.log2((d.usage_count || 0) + 1) * 4)))
      .attr('fill', (d) => RISK_COLORS[d.risk_level || 'low'] || '#cbd5e1')
      .attr('stroke', (d) => (d.is_shadow ? SHADOW_COLOR : '#0f172a'))
      .attr('stroke-width', (d) => (d.is_shadow ? 2 : 0.75))
      .attr('stroke-dasharray', (d) => (d.is_shadow ? '3,3' : '0'))
      .style('cursor', 'pointer')
      .on('click', (_e, d) => setSelected(d));

    // Tooltips
    node.append('title').text((d) =>
      `${d.name}\nrisk ${d.risk_level || 'unknown'} · ${d.usage_count} events 7d`);

    const sim = d3.forceSimulation<SimNode>(nodes)
      .force('link',   d3.forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-180))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide<SimNode>().radius((d) =>
        Math.max(10, Math.log2((d.usage_count || 0) + 1) * 4 + 10)));

    sim.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as SimNode).x!)
        .attr('y1', (d) => (d.source as SimNode).y!)
        .attr('x2', (d) => (d.target as SimNode).x!)
        .attr('y2', (d) => (d.target as SimNode).y!);
      node.attr('cx', (d) => d.x!).attr('cy', (d) => d.y!);
    });

    // Pan + zoom
    const zoomBehavior: ZoomBehavior<SVGSVGElement, unknown> = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.4, 4])
      .on('zoom', (event) => container.attr('transform', event.transform.toString()));
    svg.call(zoomBehavior).call(zoomBehavior.transform, zoomIdentity);

    return () => {
      sim.stop();
    };
  }, [nodes, links, height]);

  // Highlight nodes matching the search.
  useEffect(() => {
    if (!svgRef.current) return;
    select(svgRef.current).selectAll<SVGCircleElement, SimNode>('circle')
      .attr('opacity', (d) =>
        !query.trim() || d.name.toLowerCase().includes(query.toLowerCase())
          ? 1 : 0.2);
  }, [query, nodes]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Highlight by name…"
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <div className="flex items-center gap-2 text-xs">
          {Object.entries(RISK_COLORS).map(([k, c]) => (
            <span key={k} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-full" style={{ background: c }} /> {k}
            </span>
          ))}
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full border-2 border-dashed"
                  style={{ borderColor: SHADOW_COLOR }} /> shadow
          </span>
        </div>
        <span className="ml-auto text-xs text-slate-500">
          {nodes.length} systems · {links.length} edges
        </span>
      </div>

      <div className="relative overflow-hidden rounded-lg border bg-white" style={{ height }}>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">
            Loading…
          </div>
        )}
        {!isLoading && nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">
            No AI systems in registry yet.
          </div>
        )}
        <svg ref={svgRef} className="h-full w-full" />

        {selected && (
          <aside className="absolute right-3 top-3 w-72 rounded-lg border bg-white p-3 shadow-lg">
            <div className="flex items-start justify-between">
              <Link to={`/registry/${selected.id}`} className="font-semibold text-brand-700 hover:underline">
                {selected.name}
              </Link>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-slate-700">×</button>
            </div>
            <div className="mt-2 space-y-1 text-xs text-slate-600">
              <div><b>Category:</b> {selected.category}</div>
              <div><b>Risk:</b> {selected.risk_level ?? 'unknown'}</div>
              <div><b>Events (7d):</b> {selected.usage_count}</div>
              {selected.is_shadow && <div className="text-indigo-600 font-medium">Shadow AI</div>}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
