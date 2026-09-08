import type { ReactNode } from "react";
import { X } from "lucide-react";

type Props = { title: string; children: ReactNode; onClose: () => void };

export function Modal({ title, children, onClose }: Props) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <header><h2>{title}</h2><button className="icon-button" title="关闭" onClick={onClose}><X size={18} /></button></header>
        {children}
      </section>
    </div>
  );
}
