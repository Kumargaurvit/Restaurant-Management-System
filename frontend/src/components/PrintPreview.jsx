// Shows printer-ready text (receipt or KOT). The print stylesheet prints only this block.
export default function PrintPreview({ title, text, onClose }) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal">
        <h2>{title}</h2>
        <pre className="print-area">{text}</pre>
        <div className="row">
          <button className="button" onClick={() => window.print()}>
            Print
          </button>
          <button className="button secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
