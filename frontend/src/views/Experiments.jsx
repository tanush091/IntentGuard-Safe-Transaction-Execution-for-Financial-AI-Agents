import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { FlaskConical, RefreshCw, Table2, BarChart3, Info } from 'lucide-react';
import api from '../services/api.js';
import { Card, Empty, InlineError, Spinner, usePoll } from '../components/ui.jsx';
import { ts } from '../util.js';

const GROUP_ORDER = ['baseline', 'proposed', 'ablation'];
const GROUP_LABEL = { baseline: 'Baselines', proposed: 'Proposed', ablation: 'Ablations' };

const num = (v) => (v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v));

/** Format a metric value according to its declared unit. */
function fmtVal(v, unit, { compact = false } = {}) {
  const n = num(v);
  if (n === null) return '—';
  switch (unit) {
    case 'pct':
      return `${n.toFixed(1)}%`;
    case 'minor': {
      const major = n / 100;
      return `₹${major.toLocaleString('en-IN', { maximumFractionDigits: compact ? 0 : 2, minimumFractionDigits: compact ? 0 : 2 })}`;
    }
    case 'ms':
      return `${n.toFixed(n >= 100 ? 0 : 1)} ms`;
    case 'count':
    default:
      return Number.isInteger(n) ? String(n) : n.toFixed(2);
  }
}

/** Scale a value into the unit the chart axis uses (₹ for money). */
const chartScale = (v, unit) => (num(v) === null ? null : unit === 'minor' ? Number(v) / 100 : Number(v));

function halfWidth(m) {
  const ci = m?.ci95;
  if (!Array.isArray(ci) || ci.length < 2 || num(ci[0]) === null || num(ci[1]) === null) return null;
  return (Number(ci[1]) - Number(ci[0])) / 2;
}

function groupClass(g) {
  return GROUP_ORDER.includes(g) ? `grp-${g}` : 'grp-other';
}

export default function Experiments() {
  const { data, error, loading, reload } = usePoll(() => api.latestExperiment(), [], 0);
  const notFound = error && error.status === 404;

  const defs = data?.metric_definitions || {};
  const arms = Array.isArray(data?.arms) ? data.arms : [];
  const metricKeys = useMemo(() => {
    const keys = Object.keys(defs);
    // include metrics present on arms but missing a definition
    arms.forEach((a) => Object.keys(a?.metrics || {}).forEach((k) => { if (!keys.includes(k)) keys.push(k); }));
    return keys;
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  const groupedArms = useMemo(() => {
    const groups = {};
    arms.forEach((a) => {
      const g = a?.group || 'other';
      (groups[g] = groups[g] || []).push(a);
    });
    const order = [...GROUP_ORDER, ...Object.keys(groups).filter((g) => !GROUP_ORDER.includes(g))];
    return order.filter((g) => groups[g]).map((g) => [g, groups[g]]);
  }, [arms]);

  const best = useMemo(() => {
    const out = {};
    metricKeys.forEach((k) => {
      const better = defs[k]?.better;
      if (better !== 'lower' && better !== 'higher') return;
      const vals = arms.map((a) => num(a?.metrics?.[k]?.mean)).filter((v) => v !== null);
      if (vals.length < 2) return;
      const b = better === 'lower' ? Math.min(...vals) : Math.max(...vals);
      if (vals.every((v) => v === b)) return; // nothing to distinguish
      out[k] = b;
    });
    return out;
  }, [arms, metricKeys, defs]);

  const [metric, setMetric] = useState('');
  const [catArm, setCatArm] = useState('');
  useEffect(() => {
    if ((!metric || !metricKeys.includes(metric)) && metricKeys.length) setMetric(metricKeys[0]);
  }, [metricKeys, metric]);
  const catArms = Object.keys(data?.categories || {});
  useEffect(() => {
    if ((!catArm || !catArms.includes(catArm)) && catArms.length) {
      const proposed = arms.find((a) => a?.group === 'proposed' && catArms.includes(a.arm));
      setCatArm(proposed?.arm || catArms[0]);
    }
  }, [catArms.join('|')]); // eslint-disable-line react-hooks/exhaustive-deps

  const armLabel = (id) => arms.find((a) => a?.arm === id)?.label || id;

  const unit = defs[metric]?.unit;
  const chartData = useMemo(
    () =>
      groupedArms.flatMap(([g, list]) =>
        list.map((a) => {
          const m = a?.metrics?.[metric];
          const mean = chartScale(m?.mean, unit);
          const ci = Array.isArray(m?.ci95) ? m.ci95.map((x) => chartScale(x, unit)) : null;
          const err = mean !== null && ci && ci[0] !== null && ci[1] !== null ? [Math.max(0, mean - ci[0]), Math.max(0, ci[1] - mean)] : [0, 0];
          return { name: a.label || a.arm, arm: a.arm, group: g, mean, err, raw: m };
        }),
      ).filter((d) => d.mean !== null),
    [groupedArms, metric, unit],
  );

  if (loading && !data && !error) return <Spinner label="Loading experiment results…" />;

  if (notFound) {
    return (
      <Empty icon={<FlaskConical size={32} />} title="No benchmark results yet">
        <p>Run the benchmark from the repository root, then refresh:</p>
        <pre className="cmd">python -m bench run</pre>
        <button className="btn" onClick={reload}><RefreshCw size={14} /> Check again</button>
      </Empty>
    );
  }

  const meta = data?.meta || {};
  const metaItems = [
    ['Run id', meta.run_id],
    ['Created', typeof meta.created_at === 'number' ? ts(meta.created_at) : meta.created_at],
    ['Seeds', Array.isArray(meta.seeds) ? `${meta.seeds.length} (${meta.seeds.join(', ')})` : meta.seeds],
    ['Scenarios / seed', meta.scenarios_per_seed],
    ['Git commit', meta.git_commit],
    ['Duration', num(meta.duration_s) !== null ? `${Number(meta.duration_s).toFixed(1)} s` : null],
  ];
  const shownMeta = new Set(['run_id', 'created_at', 'seeds', 'scenarios_per_seed', 'git_commit', 'duration_s']);
  Object.entries(meta).forEach(([k, v]) => {
    if (!shownMeta.has(k)) metaItems.push([k, typeof v === 'object' ? JSON.stringify(v) : String(v)]);
  });

  const cats = data?.categories?.[catArm] || {};
  const catRows = Object.entries(cats);

  return (
    <div className="stack">
      <div className="row-between">
        <h2>Experiment results</h2>
        <button className="btn" onClick={reload}><RefreshCw size={14} /> Reload</button>
      </div>
      <InlineError error={error} onRetry={reload} />

      {data && (
        <>
          <Card title="Run metadata" icon={<Info size={16} />}>
            <dl className="meta-grid">
              {metaItems.filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd className="mono">{String(v)}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card title="Results by arm (mean ± 95% CI half-width)" icon={<Table2 size={16} />}>
            {arms.length === 0 || metricKeys.length === 0 ? (
              <div className="muted">The results file contains no arms or metrics.</div>
            ) : (
              <>
                <div className="table-wrap">
                  <table className="table results">
                    <thead>
                      <tr>
                        <th>Arm</th>
                        {metricKeys.map((k) => (
                          <th
                            key={k}
                            className={`num ${k === metric ? 'col-selected' : ''}`}
                            title={defs[k]?.description || k}
                            onClick={() => setMetric(k)}
                          >
                            {defs[k]?.label || k}
                            <span className="dir">{defs[k]?.better === 'lower' ? ' ↓' : defs[k]?.better === 'higher' ? ' ↑' : ''}</span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {groupedArms.map(([g, list]) => (
                        <React.Fragment key={g}>
                          <tr className="group-row">
                            <td colSpan={metricKeys.length + 1}>{GROUP_LABEL[g] || g}</td>
                          </tr>
                          {list.map((a) => (
                            <tr key={a.arm} className={groupClass(g)}>
                              <td>
                                <div>{a.label || a.arm}</div>
                                <div className="mono tiny muted">{a.arm}</div>
                              </td>
                              {metricKeys.map((k) => {
                                const m = a?.metrics?.[k];
                                const mean = num(m?.mean);
                                const hw = halfWidth(m);
                                const u = defs[k]?.unit;
                                const isBest = best[k] !== undefined && mean !== null && mean === best[k];
                                return (
                                  <td
                                    key={k}
                                    className={`num mono ${isBest ? 'best' : ''} ${k === metric ? 'col-selected' : ''}`}
                                    title={Array.isArray(m?.per_seed) ? `per seed: ${m.per_seed.map((x) => fmtVal(x, u)).join(', ')}${num(m?.std) !== null ? `\nstd: ${fmtVal(m.std, u)}` : ''}` : undefined}
                                  >
                                    {fmtVal(mean, u)}
                                    {hw !== null && <span className="pm"> ± {fmtVal(hw, u)}</span>}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="muted small">
                  Highlighted cells are the best arm for that metric (↓ lower is better, ↑ higher is better). Hover a
                  cell for per-seed values. Click a column header to chart it.
                </p>
              </>
            )}
          </Card>

          {metricKeys.length > 0 && (
            <Card
              title="Compare arms"
              icon={<BarChart3 size={16} />}
              actions={
                <select value={metric} onChange={(e) => setMetric(e.target.value)} aria-label="Metric">
                  {metricKeys.map((k) => <option key={k} value={k}>{defs[k]?.label || k}</option>)}
                </select>
              }
            >
              {defs[metric]?.description && <p className="muted small">{defs[metric].description}</p>}
              {chartData.length === 0 ? (
                <div className="muted">No values for this metric.</div>
              ) : (
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height={Math.max(260, chartData.length * 38 + 60)}>
                    <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 32, bottom: 8, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" horizontal={false} />
                      <XAxis
                        type="number"
                        stroke="var(--text-muted)"
                        tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                        tickFormatter={(v) => (unit === 'minor' ? fmtVal(v * 100, unit, { compact: true }) : fmtVal(v, unit))}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={190}
                        stroke="var(--text-muted)"
                        tick={{ fill: 'var(--text)', fontSize: 12 }}
                      />
                      <Tooltip
                        cursor={{ fill: 'var(--hover)' }}
                        contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }}
                        formatter={(_, __, item) => {
                          const m = item?.payload?.raw;
                          const hw = halfWidth(m);
                          return [`${fmtVal(m?.mean, unit)}${hw !== null ? ` ± ${fmtVal(hw, unit)}` : ''}`, defs[metric]?.label || metric];
                        }}
                      />
                      <Bar dataKey="mean" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                        {chartData.map((d) => (
                          <Cell key={d.arm} fill={`var(--grp-${GROUP_ORDER.includes(d.group) ? d.group : 'other'})`} />
                        ))}
                        <ErrorBar dataKey="err" width={6} strokeWidth={1.5} stroke="var(--text)" direction="x" />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  <div className="legend">
                    {groupedArms.map(([g]) => (
                      <span key={g}><i style={{ background: `var(--grp-${GROUP_ORDER.includes(g) ? g : 'other'})` }} />{GROUP_LABEL[g] || g}</span>
                    ))}
                    <span className="muted small">whiskers: 95% CI</span>
                  </div>
                </div>
              )}
            </Card>
          )}

          {catArms.length > 0 && (
            <Card
              title="Per-category results"
              icon={<Table2 size={16} />}
              actions={
                <select value={catArm} onChange={(e) => setCatArm(e.target.value)} aria-label="Arm">
                  {catArms.map((a) => <option key={a} value={a}>{armLabel(a)}</option>)}
                </select>
              }
            >
              {catRows.length === 0 ? (
                <div className="muted">No categories for this arm.</div>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th className="num">Scenarios</th>
                        <th className="num">Correct</th>
                        <th className="num">Unsafe outcomes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {catRows.map(([c, v]) => (
                        <tr key={c}>
                          <td className="mono">{c}</td>
                          <td className="num mono">{v?.scenarios ?? '—'}</td>
                          <td className="num mono">
                            {num(v?.correct_pct) !== null ? (
                              <span className="pct-cell">
                                <span className="pct-bar" style={{ width: `${Math.min(100, Math.max(0, Number(v.correct_pct)))}%` }} />
                                <span>{fmtVal(v.correct_pct, 'pct')}</span>
                              </span>
                            ) : '—'}
                          </td>
                          <td className={`num mono ${Number(v?.unsafe) > 0 ? 'text-bad' : ''}`}>{v?.unsafe ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
