import { useRestaurantLogo } from "../useRestaurantLogo.js";

// Shows printer-ready text (receipt or KOT). The print stylesheet prints only `.print-area`.
// `showLogo` puts the restaurant logo above the text (used for customer bills, not kitchen tickets).
export default function PrintPreview({ title, text, onClose, showLogo = false }) {
  const logo = useRestaurantLogo();

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal">
        <h2>{title}</h2>
        <div className="print-area">
          {showLogo && logo && <img className="print-logo" src={logo} alt="Restaurant logo" />}
          <pre>{text}</pre>
        </div>
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
