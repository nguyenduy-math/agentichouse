import { useEffect, useRef, useState } from "react";
import { getDomains, uploadDocument } from "../api/client";

export default function UploadPanel() {
  const [domains, setDomains] = useState<Record<string, string>>({});
  const [selectedDomain, setSelectedDomain] = useState("general");
  const [status, setStatus] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  const FALLBACK_DOMAINS: Record<string, string> = {
    hr: "Nhân sự và Lao động",
    legal: "Pháp lý và Tuân thủ",
    finance: "Tài chính và Kế toán",
    general: "Thông tin chung",
  };

  useEffect(() => {
    getDomains()
      .then((d) => {
        const resolved = Object.keys(d).length > 0 ? d : FALLBACK_DOMAINS;
        setDomains(resolved);
        setSelectedDomain(Object.keys(resolved)[0]);
      })
      .catch(() => {
        setDomains(FALLBACK_DOMAINS);
        setSelectedDomain("hr");
      });
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("Đang tải lên...");
    try {
      const res = await uploadDocument(file, selectedDomain);
      setStatus(`Đã tạo ${res.chunks_created} đoạn cho lĩnh vực "${res.domain}"`);
    } catch {
      setStatus("Lỗi khi tải lên. Vui lòng thử lại.");
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="border border-gray-200 rounded-lg bg-white text-sm mb-3">
      <button
        className="w-full flex justify-between items-center px-4 py-2 font-medium text-gray-700 hover:bg-gray-50 rounded-lg"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Tải lên tài liệu</span>
        <span className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3">
          <div className="flex gap-2 items-center">
            <label className="text-gray-600 shrink-0">Lĩnh vực:</label>
            <select
              className="border border-gray-300 rounded px-2 py-1 text-sm flex-1"
              value={selectedDomain}
              onChange={(e) => setSelectedDomain(e.target.value)}
            >
              {Object.entries(domains).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-2 items-center">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              className="text-sm text-gray-600 flex-1"
              onChange={handleUpload}
            />
          </div>
          {status && <p className="text-xs text-blue-600">{status}</p>}
        </div>
      )}
    </div>
  );
}
