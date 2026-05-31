import { useState, useEffect } from 'react'

const CLAIM_TYPES = [
  { value: 'outpatient', label: 'BHYT Ngoại trú' },
  { value: 'inpatient',  label: 'BHYT Nội trú' },
  { value: 'private',    label: 'Bảo hiểm thương mại' },
]

const FIELD_META = {
  name:           { label: 'Họ và tên',                          hint: 'VD: Nguyễn Văn A',                         type: 'text' },
  dob:            { label: 'Ngày sinh',                          hint: 'VD: 15/03/1990',                           type: 'text' },
  insurance_id:   { label: 'Mã số BHXH',                        hint: '10 chữ số trên thẻ BHYT',                  type: 'text' },
  policy_number:  { label: 'Số hợp đồng bảo hiểm',              hint: 'Trên thẻ/hợp đồng bảo hiểm thương mại',   type: 'text' },
  hospital:       { label: 'Cơ sở khám chữa bệnh',              hint: 'VD: Bệnh viện Bạch Mai',                   type: 'text' },
  visit_date:     { label: 'Ngày khám',                          hint: 'VD: 20/05/2025',                           type: 'text' },
  admission_date: { label: 'Ngày nhập viện',                     hint: 'VD: 10/05/2025',                           type: 'text' },
  discharge_date: { label: 'Ngày xuất viện',                     hint: 'VD: 15/05/2025',                           type: 'text' },
  event_date:     { label: 'Ngày xảy ra sự kiện',               hint: 'VD: 20/05/2025',                           type: 'text' },
  diagnosis:      { label: 'Chẩn đoán bệnh',                    hint: 'VD: Viêm phổi, gãy xương tay',             type: 'text' },
  total_cost:     { label: 'Tổng chi phí điều trị (VNĐ)',        hint: 'VD: 5000000',                              type: 'number' },
  patient_paid:   { label: 'Số tiền bệnh nhân tự trả (VNĐ)',    hint: 'Phần không được BHYT chi trả',             type: 'number' },
  bank_account:   { label: 'Số tài khoản ngân hàng',            hint: 'Để nhận hoàn tiền bảo hiểm thương mại',   type: 'text' },
}

const REQUIRED_FIELDS = {
  outpatient: ['name', 'dob', 'insurance_id', 'hospital', 'visit_date', 'diagnosis', 'total_cost'],
  inpatient:  ['name', 'dob', 'insurance_id', 'hospital', 'admission_date', 'discharge_date', 'diagnosis', 'total_cost', 'patient_paid'],
  private:    ['name', 'dob', 'policy_number', 'hospital', 'event_date', 'diagnosis', 'total_cost', 'bank_account'],
}

const FIELD_LABELS = {
  name:           'Họ và tên',
  dob:            'Ngày sinh',
  insurance_id:   'Mã số BHXH',
  policy_number:  'Số hợp đồng bảo hiểm',
  hospital:       'Cơ sở khám chữa bệnh',
  visit_date:     'Ngày khám',
  admission_date: 'Ngày nhập viện',
  discharge_date: 'Ngày xuất viện',
  event_date:     'Ngày xảy ra sự kiện',
  diagnosis:      'Chẩn đoán bệnh',
  total_cost:     'Tổng chi phí (VNĐ)',
  patient_paid:   'Bệnh nhân tự trả (VNĐ)',
  bank_account:   'Số tài khoản ngân hàng',
}

export default function ClaimForm({ externalFields, onProgressChange }) {
  const [claimType, setClaimType] = useState(null)
  const [fields, setFields] = useState({})
  const [submitted, setSubmitted] = useState(false)

  // Sync fields populated by the chat bot
  useEffect(() => {
    if (!externalFields) return
    setFields(prev => {
      const next = { ...prev }
      Object.entries(externalFields).forEach(([k, v]) => {
        if (v != null && v !== '' && String(v).trim() !== '') {
          next[k] = String(v)
        }
      })
      return next
    })
    // If chat populated claim_type, sync it
    if (externalFields.claim_type && externalFields.claim_type !== 'unknown') {
      setClaimType(externalFields.claim_type)
    }
  }, [externalFields])

  const requiredFields = claimType ? REQUIRED_FIELDS[claimType] : []
  const filledCount = requiredFields.filter(f => fields[f]?.trim()).length
  const progressPct = requiredFields.length ? Math.round(filledCount * 100 / requiredFields.length) : 0

  useEffect(() => {
    onProgressChange?.(progressPct)
  }, [progressPct])

  function handleField(name, value) {
    setFields(prev => ({ ...prev, [name]: value }))
  }

  function handleSubmit(e) {
    e.preventDefault()
    setSubmitted(true)
  }

  function handleReset() {
    setSubmitted(false)
  }

  const inputStyle = {
    width: '100%', padding: '9px 12px', border: '1px solid #d1d5db',
    borderRadius: 8, fontSize: 14, outline: 'none', fontFamily: 'inherit',
    boxSizing: 'border-box',
  }
  const labelStyle = { display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }
  const hintStyle  = { fontSize: 12, color: '#9ca3af', marginTop: 3 }

  // --- Summary card ---
  if (submitted && claimType) {
    const claimLabel = CLAIM_TYPES.find(t => t.value === claimType)?.label
    return (
      <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 12, padding: 24 }}>
        <div style={{ fontWeight: 700, fontSize: 16, color: '#15803d', marginBottom: 16 }}>✅ Xác nhận thông tin khai thác</div>
        <div style={{ background: '#fff', borderRadius: 8, overflow: 'hidden', border: '1px solid #e5e7eb' }}>
          <div style={{ background: '#3b82f6', color: '#fff', padding: '10px 16px', fontWeight: 600, fontSize: 13 }}>
            {claimLabel}
          </div>
          {requiredFields.map(f => (
            <div key={f} style={{ display: 'flex', padding: '10px 16px', borderBottom: '1px solid #f3f4f6' }}>
              <div style={{ width: 200, fontSize: 13, color: '#6b7280', flexShrink: 0 }}>{FIELD_LABELS[f]}</div>
              <div style={{ fontSize: 13, fontWeight: 500, color: fields[f] ? '#111827' : '#ef4444' }}>
                {fields[f] || '(chưa điền)'}
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16, display: 'flex', gap: 10 }}>
          <button onClick={handleReset} style={{ padding: '9px 20px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', cursor: 'pointer', fontSize: 14 }}>
            Chỉnh sửa
          </button>
          <button style={{ padding: '9px 20px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>
            Nộp hồ sơ
          </button>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit}>
      {/* Claim type selector */}
      <div style={{ marginBottom: 20 }}>
        <div style={labelStyle}>Loại hình bảo hiểm <span style={{ color: '#ef4444' }}>*</span></div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {CLAIM_TYPES.map(t => (
            <button
              type="button"
              key={t.value}
              onClick={() => { setClaimType(t.value); setSubmitted(false) }}
              style={{
                padding: '8px 18px', borderRadius: 8, border: '2px solid',
                borderColor: claimType === t.value ? '#3b82f6' : '#d1d5db',
                background: claimType === t.value ? '#eff6ff' : '#fff',
                color: claimType === t.value ? '#1d4ed8' : '#374151',
                fontWeight: claimType === t.value ? 700 : 400,
                cursor: 'pointer', fontSize: 14, transition: 'all .15s',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Progress bar */}
      {claimType && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7280', marginBottom: 6 }}>
            <span>Tiến độ điền thông tin</span>
            <span style={{ fontWeight: 600, color: progressPct === 100 ? '#16a34a' : '#3b82f6' }}>{progressPct}%</span>
          </div>
          <div style={{ height: 6, background: '#e5e7eb', borderRadius: 99 }}>
            <div style={{
              height: '100%', borderRadius: 99, transition: 'width .3s',
              width: `${progressPct}%`,
              background: progressPct === 100 ? '#16a34a' : '#3b82f6',
            }} />
          </div>
        </div>
      )}

      {/* Dynamic fields */}
      {claimType && (
        <div style={{ display: 'grid', gap: 16 }}>
          {requiredFields.map(f => {
            const meta = FIELD_META[f]
            return (
              <div key={f}>
                <label style={labelStyle}>
                  {meta.label} <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type={meta.type}
                  value={fields[f] ?? ''}
                  onChange={e => handleField(f, e.target.value)}
                  placeholder={meta.hint}
                  style={inputStyle}
                />
              </div>
            )
          })}

          <button
            type="submit"
            style={{
              marginTop: 4, padding: '11px 24px', background: '#3b82f6', color: '#fff',
              border: 'none', borderRadius: 8, fontWeight: 700, fontSize: 15,
              cursor: 'pointer', transition: 'background .15s',
            }}
          >
            Xem lại & Xác nhận
          </button>
        </div>
      )}
    </form>
  )
}
