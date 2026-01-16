import { useState } from "react";

export default function App() {
  const [formData, setFormData] = useState({
    gasto_id: "",
    empleado_id: "",
    empleado_nombre: "",
    empleado_apellido: "",
    empleado_cost_center: "",
    categoria: "",
    moneda: "USD",
    monto: "",
    fecha: "",
  });

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);

    try {
      const res = await fetch("/api/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      const data = await res.json();
      setResult(data);
    } catch (err) {
      setResult({ error: "Network or server error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 720, margin: "40px auto", fontFamily: "system-ui" }}>
      <h2>Xpendit | Validar Gasto</h2>

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 10, marginTop: 16 }}>
        <input name="gasto_id" placeholder="gasto_id" value={formData.gasto_id} onChange={handleChange} required />
        <input name="empleado_id" placeholder="empleado_id" value={formData.empleado_id} onChange={handleChange} required />
        <input name="empleado_nombre" placeholder="empleado_nombre" value={formData.empleado_nombre} onChange={handleChange} />
        <input name="empleado_apellido" placeholder="empleado_apellido" value={formData.empleado_apellido} onChange={handleChange} />
        <input name="empleado_cost_center" placeholder="empleado_cost_center" value={formData.empleado_cost_center} onChange={handleChange} required />
        <input name="categoria" placeholder="categoria (food/transport/...)" value={formData.categoria} onChange={handleChange} required />

        <select name="moneda" value={formData.moneda} onChange={handleChange}>
          <option value="USD">USD</option>
          <option value="CLP">CLP</option>
          <option value="EUR">EUR</option>
          <option value="MXN">MXN</option>
        </select>

        <input type="number" step="0.01" name="monto" placeholder="monto" value={formData.monto} onChange={handleChange} required />
        <input name="fecha" placeholder="fecha (YYYY-MM-DD)" value={formData.fecha} onChange={handleChange} required />

        <button type="submit" disabled={loading} style={{ padding: 10, cursor: "pointer" }}>
          {loading ? "Validando..." : "Validar"}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: 20, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          {result.error ? (
            <div style={{ color: "crimson" }}>{result.error}</div>
          ) : (
            <>
              <div>
                <strong>Status:</strong> {result.status}
              </div>

              <div style={{ marginTop: 10 }}>
                <strong>Alertas:</strong>
                {result.alertas && result.alertas.length > 0 ? (
                  <ul>
                    {result.alertas.map((a, idx) => (
                      <li key={idx}>
                        <strong>{a.codigo}</strong>: {a.mensaje}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div>(sin alertas)</div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
