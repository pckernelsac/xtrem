import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { RequireAuth, RequirePermission } from "@/components/auth/RequireAuth"
import { AppLayout } from "@/components/layout/AppLayout"
import BicicletaDetailPage from "@/pages/BicicletaDetailPage"
import BicicletasPage from "@/pages/BicicletasPage"
import ClienteDetailPage from "@/pages/ClienteDetailPage"
import ClientesPage from "@/pages/ClientesPage"
import DashboardPage from "@/pages/DashboardPage"
import FichaDetailPage from "@/pages/FichaDetailPage"
import FichaFormPage from "@/pages/FichaFormPage"
import FichasPage from "@/pages/FichasPage"
import InventarioPage from "@/pages/InventarioPage"
import KardexPage from "@/pages/KardexPage"
import AuditoriaPage from "@/pages/AuditoriaPage"
import CajaPage from "@/pages/CajaPage"
import DocumentoDetailPage from "@/pages/DocumentoDetailPage"
import DocumentosPage from "@/pages/DocumentosPage"
import LoginPage from "@/pages/LoginPage"
import PuntoVentaPage from "@/pages/PuntoVentaPage"
import ReportesPage from "@/pages/ReportesPage"
import VentaDetailPage from "@/pages/VentaDetailPage"
import VentasPage from "@/pages/VentasPage"
import RolesPage from "@/pages/RolesPage"
import UsuariosPage from "@/pages/UsuariosPage"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPage />} />

          <Route
            path="clientes"
            element={
              <RequirePermission permission="clientes.ver">
                <ClientesPage />
              </RequirePermission>
            }
          />
          <Route
            path="clientes/:id"
            element={
              <RequirePermission permission="clientes.ver">
                <ClienteDetailPage />
              </RequirePermission>
            }
          />
          <Route
            path="bicicletas"
            element={
              <RequirePermission permission="bicicletas.ver">
                <BicicletasPage />
              </RequirePermission>
            }
          />
          <Route
            path="bicicletas/:id"
            element={
              <RequirePermission permission="bicicletas.ver">
                <BicicletaDetailPage />
              </RequirePermission>
            }
          />

          {/* "nueva" antes que ":id": si no, el detalle capturaría esa ruta. */}
          <Route
            path="fichas"
            element={
              <RequirePermission permission="fichas.ver">
                <FichasPage />
              </RequirePermission>
            }
          />
          <Route
            path="fichas/nueva"
            element={
              <RequirePermission permission="fichas.crear">
                <FichaFormPage />
              </RequirePermission>
            }
          />
          <Route
            path="fichas/:id"
            element={
              <RequirePermission permission="fichas.ver">
                <FichaDetailPage />
              </RequirePermission>
            }
          />
          <Route
            path="fichas/:id/editar"
            element={
              <RequirePermission permission="fichas.editar">
                <FichaFormPage />
              </RequirePermission>
            }
          />

          {/* "kardex" antes que cualquier ruta con parámetro de inventario. */}
          <Route
            path="inventario"
            element={
              <RequirePermission permission="inventario.ver">
                <InventarioPage />
              </RequirePermission>
            }
          />
          <Route
            path="inventario/kardex"
            element={
              <RequirePermission permission="inventario.ver">
                <KardexPage />
              </RequirePermission>
            }
          />

          <Route
            path="ventas"
            element={
              <RequirePermission permission="ventas.ver">
                <VentasPage tipo="VENTA" />
              </RequirePermission>
            }
          />
          <Route
            path="ventas/nueva"
            element={
              <RequirePermission permission="ventas.crear">
                <PuntoVentaPage />
              </RequirePermission>
            }
          />
          <Route
            path="ventas/:id/editar"
            element={
              <RequirePermission permission="ventas.editar">
                <PuntoVentaPage />
              </RequirePermission>
            }
          />
          <Route
            path="ventas/:id"
            element={
              <RequirePermission permission="ventas.ver">
                <VentaDetailPage />
              </RequirePermission>
            }
          />
          <Route
            path="cotizaciones"
            element={
              <RequirePermission permission="ventas.ver">
                <VentasPage tipo="COTIZACION" />
              </RequirePermission>
            }
          />
          <Route
            path="caja"
            element={
              <RequirePermission permission="caja.ver">
                <CajaPage />
              </RequirePermission>
            }
          />
          <Route
            path="documentos"
            element={
              <RequirePermission permission="facturacion.ver">
                <DocumentosPage />
              </RequirePermission>
            }
          />
          <Route
            path="documentos/:id"
            element={
              <RequirePermission permission="facturacion.ver">
                <DocumentoDetailPage />
              </RequirePermission>
            }
          />

          <Route
            path="reportes"
            element={
              <RequirePermission permission="reportes.ver">
                <ReportesPage />
              </RequirePermission>
            }
          />

          <Route
            path="usuarios"
            element={
              <RequirePermission permission="usuarios.ver">
                <UsuariosPage />
              </RequirePermission>
            }
          />
          <Route
            path="roles"
            element={
              <RequirePermission permission="roles.ver">
                <RolesPage />
              </RequirePermission>
            }
          />
          <Route
            path="auditoria"
            element={
              <RequirePermission permission="auditoria.ver">
                <AuditoriaPage />
              </RequirePermission>
            }
          />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
