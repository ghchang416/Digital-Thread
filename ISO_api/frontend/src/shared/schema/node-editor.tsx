import { useState } from 'react';
import { ArrowDown, ArrowUp, ArrowRight, Plus, Trash2 } from 'lucide-react';
import { isRef } from './types';
import type { Catalog, Draft, Field, FieldValue, Scalar } from './types';
import { newId, nodeTitle } from '../draft/model';
import type { Command } from '../draft/model';
import { SelectionDialog } from '../ui/selection-dialog';
import type { CamOrigin } from '../../features/cam/types';
import { completionLabels, formatValue } from '../../features/completion/model';
import { pickerPolicy } from '../draft/references';
import { ReferencePicker } from './reference-picker';

interface Props {
  draft: Draft; catalog: Catalog; nodeId: string; dispatch: (command: Command) => void;
  navigate: (id: string) => void; rawInputs: Record<string, string>;
  setRaw: (key: string, value?: string) => void;
  extras: string[]; setExtras: (values: string[]) => void;
  origins?: CamOrigin[];
  hiddenFields?: string[];
  openAsset: (id: string) => void;
  labels?: Record<string, string>;
}

export function NodeEditor({ draft, catalog, nodeId, dispatch, navigate, rawInputs, setRaw, extras, setExtras, origins = [], hiddenFields = [], openAsset, labels = {} }: Props) {
  const node = draft.nodes[nodeId];
  const type = catalog.types[node.typeId];
  const [dialog, setDialog] = useState<'field' | Field | null>(null);
  const rootHiddenFields = draft.assets.some(asset => asset.elementNodeId === nodeId) ? hiddenFields : [];
  const editable = type.fields.filter(f => (!f.managed || pickerPolicy(catalog, f)) && !rootHiddenFields.includes(f.fieldName)).map(f => labels[f.fieldName] ? { ...f, label: labels[f.fieldName] } : f);
  const fields = editable.filter(f => f.required || f.fieldName in node.fields || extras.includes(f.fieldName) || draft.referenceLinks?.some(link => link.sourceNodeId === nodeId && link.policyId === f.referencePolicyId));
  const optional = editable.filter(f => !f.required && !fields.includes(f));
  const setValue = (field: string, value?: FieldValue) => dispatch({ kind: 'set', nodeId, field, value });
  const removeField = (name: string) => {
    setExtras(extras.filter(item => item !== name));
    for (const key of Object.keys(rawInputs)) if (key.startsWith(`${nodeId}:${name}:`)) setRaw(key);
    const policy = pickerPolicy(catalog, type.fields.find(f => f.fieldName === name)!);
    if (policy) dispatch({ kind: 'reference', nodeId, policyId: policy.id, policyHash: catalog.referencePolicyHash! });
    else setValue(name);
  };
  function scalarInput(field: Field, value: unknown, onChange: (value: Scalar | undefined) => void, itemId = '') {
    const key = `${nodeId}:${field.fieldName}:${itemId}`;
    const id = `field-${nodeId}-${field.fieldName}-${itemId}`;
    const label = field.label;
    if (field.kind === 'enum' || field.scalarTypes.includes('bool')) {
      const values = field.kind === 'enum' ? catalog.enums[field.enumTypes[0]] : ['true', 'false'];
      return <select id={id} aria-label={label} value={value === undefined ? '' : String(value)} onChange={e => onChange(e.target.value === '' ? undefined : field.kind === 'enum' ? e.target.value : e.target.value === 'true')}>
        <option value="">선택 안 함</option>{values.map(v => <option key={v} value={v}>{field.kind === 'enum' ? v : v === 'true' ? '예' : '아니오'}</option>)}
      </select>;
    }
    const numeric = field.scalarTypes.some(t => t === 'int' || t === 'float');
    return <input id={id} className={numeric ? 'numeric-input' : ''} aria-label={label} inputMode={numeric ? 'decimal' : undefined}
      aria-invalid={key in rawInputs} value={rawInputs[key] ?? (typeof value === 'string' || typeof value === 'number' ? value : '')}
      onChange={e => {
        const text = e.target.value;
        if (!numeric) { onChange(text); return; }
        if (!text.trim()) { setRaw(key); onChange(undefined); return; }
        const num = Number(text);
        if (!Number.isFinite(num) || (field.scalarTypes.includes('int') && !Number.isInteger(num))) { setRaw(key, text); return; }
        setRaw(key); onChange(num);
      }} />;
  }
  return <section className="node-editor">
    <div className="section-heading"><div><h2>{nodeTitle(node, catalog)}</h2><span className="type-name">{type.label} · {type.xmlName}</span></div>
      <button className="secondary" onClick={() => setDialog('field')} disabled={!optional.length}><Plus size={16} />항목 추가</button></div>
    <div className="field-list">{fields.map(field => {
      const policy = pickerPolicy(catalog, field);
      const value = node.fields[field.fieldName];
      const origin = origins.find(item => item.fieldName === field.fieldName);
      const completion = draft.completionEntries?.find(item => item.nodeId === nodeId && item.fieldName === field.fieldName);
      const pendingInput = Object.keys(rawInputs).some(key => key.startsWith(`${nodeId}:${field.fieldName}:`));
      const items = Array.isArray(value) ? value : [];
      const canAdd = field.maxOccurs === null || items.length < field.maxOccurs;
      const hint = policy ? '자산 참조 · 선택 0..1' : field.kind === 'object' ? '객체' : field.kind === 'enum' ? '선택값' : field.scalarTypes.includes('bool') ? '예 / 아니오' : field.scalarTypes.includes('int') ? '정수' : field.scalarTypes.includes('float') ? '실수' : '문자열';
      return <div className="field" key={field.fieldName} id={`row-${nodeId}-${field.fieldName}`}>
        <div className="field-heading"><div><label htmlFor={`field-${nodeId}-${field.fieldName}-`}>{field.label}{field.required && <span className="required"> *</span>}</label><small>{hint}{field.repeated ? ` · 반복 ${field.minOccurs}..${field.maxOccurs ?? 'N'}` : ''}{field.label !== field.fieldName ? ` · ${field.fieldName}` : ''}</small></div>
          {!field.required && <button className="icon-button" title="항목 삭제" aria-label={`${field.label} 삭제`} onClick={() => removeField(field.fieldName)}><Trash2 size={15} /></button>}</div>
        <div className="field-control">{policy ? <ReferencePicker draft={draft} catalog={catalog} nodeId={nodeId} policy={policy} openAsset={openAsset} onChange={targetAssetNodeId => dispatch({ kind: 'reference', nodeId, policyId: policy.id, targetAssetNodeId, policyHash: catalog.referencePolicyHash! })} /> : field.repeated ? <div className="repeated">
          {items.map((item, index) => <div className="repeat-row" key={isRef(item) ? item.$node : item.itemId}>
            <span className="row-number">{index + 1}</span>
            {isRef(item) ? <button className="object-link" onClick={() => navigate(item.$node)}><span>{nodeTitle(draft.nodes[item.$node], catalog)}</span><ArrowRight size={16} /></button> : scalarInput(field, item.value, next => {
              const changed = [...items]; changed[index] = { ...item, value: next ?? '' }; setValue(field.fieldName, changed);
            }, item.itemId)}
            <div className="row-actions">
              <button className="icon-button" title="위로" aria-label={`${field.label} ${index + 1} 위로`} disabled={index === 0} onClick={() => dispatch({ kind: 'move', nodeId, field: field.fieldName, index, direction: -1 })}><ArrowUp size={15} /></button>
              <button className="icon-button" title="아래로" aria-label={`${field.label} ${index + 1} 아래로`} disabled={index === items.length - 1} onClick={() => dispatch({ kind: 'move', nodeId, field: field.fieldName, index, direction: 1 })}><ArrowDown size={15} /></button>
              <button className="icon-button" title="삭제" aria-label={`${field.label} ${index + 1} 삭제`} disabled={items.length <= field.minOccurs} onClick={() => { if (!isRef(item)) setRaw(`${nodeId}:${field.fieldName}:${item.itemId}`); dispatch({ kind: 'remove-item', nodeId, field: field.fieldName, index }); }}><Trash2 size={15} /></button>
            </div>
          </div>)}
          <button className="text-button" disabled={!canAdd} onClick={() => field.kind === 'object' ? setDialog(field) : setValue(field.fieldName, [...items, { itemId: newId(), value: '' }])}><Plus size={16} />{field.label} 추가</button>
        </div> : field.kind === 'object' ? isRef(value) ? <div className="object-row"><button className="object-link" onClick={() => navigate(value.$node)}><span>{nodeTitle(draft.nodes[value.$node], catalog)}</span><ArrowRight size={16} /></button><button className="text-button" onClick={() => { if (confirm('객체 타입을 변경하면 현재 하위 입력값이 삭제됩니다. 계속할까요?')) setDialog(field); }}>타입 변경</button></div> : <button className="secondary" onClick={() => setDialog(field)}><Plus size={16} />타입 선택</button> : scalarInput(field, value, next => setValue(field.fieldName, next))}
        {origin && <small className="origin-note" title={`${origin.sourcePath}: ${JSON.stringify(origin.value)}`}>{pendingInput ? `숫자 입력 확인 필요 · CAM 원본 ${String(origin.value)}` : JSON.stringify(value) === JSON.stringify(origin.value) ? 'CAM 가져온 값' : `CAM 원본에서 수정됨 · 원본 ${String(origin.value)}`}</small>}
        {completion && <small className={`origin-note completion-badge ${completion.kind}`} title={`${completion.reason} 최초 값: ${formatValue(completion.value, draft)}`}>{completionLabels[completion.kind]}{pendingInput ? ' · 숫자 입력 확인 필요' : JSON.stringify(value) !== JSON.stringify(completion.value) ? ' · 보완 후 변경됨' : ''} · {completion.reason}</small>}</div>
      </div>;
    })}</div>
    {!fields.length && <p className="empty">입력 항목이 없습니다.</p>}
    {dialog && <SelectionDialog title={dialog === 'field' ? '추가할 항목' : `${dialog.label} 타입`} choices={dialog === 'field' ? optional.map(f => ({ id: f.fieldName, title: f.label, detail: `${f.fieldName} · ${f.repeated ? '반복' : '단일'} · ${f.kind}` })) : [...new Set(dialog.objectTypes.flatMap(base => [base, ...catalog.types[base].descendants]))].map(id => ({ id, title: catalog.types[id].label, detail: catalog.types[id].xmlName }))}
      onClose={() => setDialog(null)} onSelect={id => { if (dialog === 'field') setExtras([...extras, id]); else dispatch({ kind: 'attach', nodeId, field: dialog.fieldName, typeId: id, repeated: dialog.repeated }); }} />}
  </section>;
}
