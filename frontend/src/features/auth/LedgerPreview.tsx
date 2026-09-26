const LINES: { step: string; detail: string; status: string; tone: string }[] = [
  { step: 'linking', detail: 'orders · order_items · stores · regions', status: '38ms', tone: 'text-[#8DB872]' },
  { step: 'generate', detail: 'claude-sonnet-5 · self_conf 0.88', status: '1.2s', tone: 'text-[#8DB872]' },
  { step: 'validate', detail: 'SELECT-only · allowlist · LIMIT 1000', status: 'ok', tone: 'text-[#8DB872]' },
  { step: 'judge', detail: 'gpt · rubric 4.6/5 · pass', status: '0.92', tone: 'text-[#8DB872]' },
  { step: 'gate', detail: 'AUTO_EXECUTE', status: '→', tone: 'text-[#6D8BFF]' },
]

export function LedgerPreview() {
  return (
    <figure aria-hidden className="font-mono text-[12.5px] leading-7">
      <p className="ledger-line text-[#ECEAE4]" style={{ animationDelay: '120ms' }}>
        <span className="text-[#737883]">›</span> Doanh thu theo khu vực quý này?
      </p>
      <div className="mt-3 border-l border-[#2C3037] pl-4">
        {LINES.map((line, i) => (
          <p key={line.step} className="ledger-line grid grid-cols-[80px_1fr_auto] gap-4" style={{ animationDelay: `${420 + i * 260}ms` }}>
            <span className="text-[#737883]">{line.step}</span>
            <span className="truncate text-[#A9ADB6]">{line.detail}</span>
            <span className={line.tone}>{line.status}</span>
          </p>
        ))}
      </div>
    </figure>
  )
}
