## DOCUMENTACIÓN

### Descripción
Esto es un software que permite obtener datos de una factura de **Holded** y de un contacto de **Cegid Diez**, para luego sincronizarlos en este último.

---

## Documentación API de Holded

- **Obtener listado de facturas (documentos)**  
  https://developers.holded.com/reference/list-documents-1

- **Detalle de una factura (documento)**  
  https://developers.holded.com/reference/getdocument-1

- **Detalle del contacto / Listarlo**  
  https://developers.holded.com/reference/getcontact-1  
  https://developers.holded.com/reference/list-contacts-1  

- **Obtener pagos de una factura**  
  https://developers.holded.com/reference/list-payments

- **Obtener impuestos (IVA, IRPF, etc.)**  
  https://developers.holded.com/reference/gettax-1

---

## Documentación API de Cegid Diez

### Descripción
Para integrar datos desde **Holded** a **Cegid Diez**, es necesario crear tanto los **clientes** como las **facturas** en Cegid Diez.

- 📄 **Documentación API de Cegid Diez**  
  https://apicon.diezsoftware.com/swagger/

### 🔹 **Clientes en Cegid Diez**
- **Añadir cliente**  
  POST https://apicon.diezsoftware.com/swagger/#!/Clientes/Clientes_Post  
- **Actualizar cliente**  
  PUT https://apicon.diezsoftware.com/swagger/#!/Clientes/Clientes_Put  

### 🔹 **Facturas en Cegid Diez**
- **Crear factura**  
  POST https://apicon.diezsoftware.com/swagger/#!/Facturas/Facturas_Post  
- **Actualizar factura**  
  PUT https://apicon.diezsoftware.com/swagger/#!/Facturas/Facturas_Put  
- **Consultar facturas existentes**  
  GET https://apicon.diezsoftware.com/swagger/#!/Facturas/Facturas_Get  

---

## Datos de una factura

### **Datos del Emisor (contacto en Holded)**
- **Número de identificación fiscal (NIF, CIF, DNI, RFC)**
- **Nombre o Razón Social**
- **Dirección fiscal**
- **Teléfono | Correo electrónico (opcional)**

### **Datos del Receptor (cliente en Cegid Diez)**
- **Número de identificación fiscal (NIF, CIF, DNI, RFC)**
- **Nombre o Razón Social**
- **Dirección fiscal**
- **Teléfono | Correo electrónico (opcional)**

### **Datos de la Factura**
- **Número de factura** (`docNumber`)
- **Fecha de emisión** (`date`)
- **Fecha de vencimiento** (`dueDate`)
- **Estado de la factura** (`status`)
- **Moneda** (`currency`)
- **Subtotal** (`subtotal`)
- **Impuestos aplicados** (`tax`)
- **Total de la factura** (`total`)
- **Método de pago y estado de pago**
- **Lista de productos o servicios vendidos**
  - Nombre del producto (`name`)
  - Descripción (`desc`)
  - Precio unitario (`price`)
  - Cantidad (`units`)
  - Impuestos aplicados (`tax`)
  - Código SKU (`sku`)
  - Descuentos aplicados (`discount`)

# 📌 Documentación: Facturas en Cegid Diez API

---

## 🧾 **Estructura de una Factura en Cegid Diez API**
### **Campos Principales**
| Campo                          | Tipo      | Obligatorio | Descripción |
|--------------------------------|----------|------------|-------------|
| `Ejercicio`                    | string   | ✅ Sí      | Año contable de la factura. |
| `Serie`                        | string   | ✅ Sí      | Serie a la que pertenece la factura. |
| `Documento`                    | integer  | ❌ No      | Número de documento de la factura (opcional). |
| `TipoAsiento`                  | string   | ✅ Sí      | Tipo de asiento contable. Valores posibles: `Asiento`, `FacturasEmitidas`, `FacturasRecibidas`, `AsientoApertura`, `AsientoPyG`, `AsientoCierre`. |
| `Fecha`                        | integer  | ✅ Sí      | Fecha del asiento (timestamp). |
| `CuentaCliente`                | string   | ✅ Sí      | Código de la cuenta contable del cliente. |
| `FechaFactura`                 | integer  | ❌ No      | Fecha de la factura (timestamp). |
| `FechaIntroduccionFactura`      | integer  | ❌ No      | Fecha de introducción de la factura (si es diferente de `FechaFactura`). |
| `FechaOperacion`               | integer  | ❌ No      | Fecha de operación de la factura (si es diferente de `FechaFactura`). |
| `Descripcion`                  | string   | ❌ No      | Descripción general de la factura. |
| `BaseImponible1`               | number   | ❌ No      | Importe de la base imponible 1. |
| `BaseImponible2`               | number   | ❌ No      | Importe de la base imponible 2. |
| `BaseImponible3`               | number   | ❌ No      | Importe de la base imponible 3. |
| `BaseImponible4`               | number   | ❌ No      | Importe de la base imponible 4. |
| `CuotaIVA1`                    | number   | ❌ No      | Cuota de IVA aplicada en la base imponible 1. |
| `CuotaIVA2`                    | number   | ❌ No      | Cuota de IVA aplicada en la base imponible 2. |
| `CuotaIVA3`                    | number   | ❌ No      | Cuota de IVA aplicada en la base imponible 3. |
| `CuotaIVA4`                    | number   | ❌ No      | Cuota de IVA aplicada en la base imponible 4. |
| `TotalFactura`                 | number   | ❌ No      | Importe total de la factura. |
| `NombreCliente`                | string   | ❌ No      | Nombre del cliente. |
| `CifCliente`                   | string   | ❌ No      | Número de Identificación Fiscal (NIF) del cliente. |

---


## 🏷️ **Tipos de Factura en Cegid Diez**
| Tipo de Factura | Descripción |
|----------------|------------|
| `OpInteriores` | Operaciones interiores. |
| `EntregasAdquisicionesIntracomunitarias` | Transacciones intracomunitarias. |
| `ExportacionesImportaciones` | Facturas de importación/exportación. |
| `OpInteriorBienesInversion` | Operaciones de bienes de inversión. |
| `Certificaciones` | Facturas de certificaciones. |
| `InversionSujetoPasivoOpNosujetas` | Inversión de sujeto pasivo. |
| `EntrabasAdquiscionesIntracomunitariasDeServicios` | Adquisiciones intracomunitarias de servicios. |
| `ModificacionesDeBasesYCoutas` | Modificaciones de bases y cuotas. |

---

## 🔄 **Cómo Mapear Datos de Holded con Cegid Diez**
| **Campo en Holded**      | **Campo en Cegid Diez**   | **Notas** |
|--------------------------|--------------------------|-----------|
| `docNumber`             | `Documento`              | Número de la factura en Holded. |
| `date`                  | `FechaFactura`           | Convertir a timestamp si es necesario. |
| `dueDate`               | `FechaOperacion`         | Fecha de vencimiento en Holded. |
| `contactName`           | `NombreCliente`          | Nombre del cliente en Holded. |
| `contactId`             | `CuentaCliente`          | Se debe mapear con el identificador de cliente en Cegid. |
| `currency`              | _Pendiente de definir_   | Cegid podría manejarlo en otra estructura. |
| `subtotal`              | `BaseImponible1`         | Si hay varios tipos de IVA, dividir en `BaseImponible1`, `BaseImponible2`, etc. |
| `tax`                   | `CuotaIVA1`              | Si hay múltiples tasas de IVA, separarlas en `CuotaIVA1`, `CuotaIVA2`, etc. |
| `total`                 | `TotalFactura`           | Importe total de la factura. |
| `status`                | _Pendiente de definir_   | Estado de la factura en Holded, confirmar si Cegid necesita este dato. |

---

## ⚠️ **Consideraciones Importantes**
1. **Fechas en timestamp**  
   - Holded usa fechas en formato ISO 8601 (`YYYY-MM-DD`), mientras que Cegid usa **timestamps**. Se debe convertir antes de enviar los datos.
   
2. **Conversión de Impuestos (IVA y Recargo de Equivalencia)**  
   - Holded maneja `tax`, mientras que en Cegid cada base imponible y cuota de IVA están separadas en `BaseImponible1`, `BaseImponible2`, etc.
   - Si en Holded hay diferentes tipos de IVA en una misma factura, se debe dividir en varias líneas en Cegid.

3. **Creación de Clientes Antes de Facturas**  
   - Antes de enviar una factura a Cegid, el cliente **debe existir** en su sistema. Si no está, se debe crear usando `POST /Clientes`.

4. **Validaciones Previas al Envío a Cegid**  
   - Se recomienda verificar que los datos de la factura sean correctos y completos antes de enviarlos a Cegid para evitar errores.


---

## 🏷️ **Estructura del Cliente en Cegid Diez API**
### **Campos Principales**
| Campo                          | Tipo      | Obligatorio | Descripción |
|--------------------------------|----------|------------|-------------|
| `Codigo`                       | integer  | ✅ Sí      | Código único del cliente en Cegid. |
| `NombreFiscal`                 | string   | ✅ Sí      | Razón social del cliente. |
| `NombreComercial`              | string   | ✅ Sí      | Nombre comercial del cliente. |
| `CIF`                          | string   | ✅ Sí      | Número de Identificación Fiscal (NIF, CIF, RFC, etc.). |
| `Direccion`                    | string   | ❌ No      | Dirección fiscal del cliente. |
| `CodigoPostal`                 | integer  | ❌ No      | Código postal del cliente. |
| `Poblacion`                    | string   | ❌ No      | Ciudad del cliente. |
| `Provincia`                    | string   | ❌ No      | Provincia o estado del cliente. |
| `Telefono`                     | string   | ❌ No      | Número de teléfono del cliente. |
| `AplicarRetencion`             | boolean  | ❌ No      | Si el cliente está sujeto a retención fiscal. |
| `AplicarRecargoEquivalencia`    | boolean  | ❌ No      | Indica si el cliente está sujeto a recargo de equivalencia. |
| `GrupoIngresos`                | string   | ❌ No      | Grupo contable de ingresos del cliente. |
| `Fax`                          | string   | ❌ No      | Número de fax del cliente. |
| `ClienteGenerico`              | boolean  | ❌ No      | Si es un cliente genérico o no. |
| `NoIncluir347`                 | boolean  | ❌ No      | Si se debe excluir de la declaración 347. |
| `NoActivo`                     | boolean  | ❌ No      | Indica si el cliente está inactivo. |
| `Pais`                         | string   | ❌ No      | Código de país del cliente (ejemplo: "ES" para España). |
| `Mail`                         | string   | ❌ No      | Correo electrónico del cliente. |
| `Empresa`                      | integer  | ❌ No      | No se debe informar, se rellena automáticamente. |
| `TipoIdentificador`            | integer  | ❌ No      | Tipo de documento de identificación fiscal (DNI, CIF, etc.). |

---

## 🔄 **Cómo Mapear Datos de Holded con Cegid Diez**
| **Campo en Holded**    | **Campo en Cegid Diez**  | **Notas** |
|------------------------|-------------------------|-----------|
| `contactId`           | `Codigo`                | ID del cliente en Holded, se usará como identificador en Cegid. |
| `name`                | `NombreFiscal`          | Razón social del cliente en Holded. |
| `name`                | `NombreComercial`       | Nombre comercial (puede ser el mismo que la razón social). |
| `vatNumber`           | `CIF`                   | Número de identificación fiscal (NIF, CIF, RFC). |
| `address.street`      | `Direccion`             | Dirección fiscal. |
| `address.zipcode`     | `CodigoPostal`          | Código postal. |
| `address.city`        | `Poblacion`             | Ciudad. |
| `address.province`    | `Provincia`             | Provincia o estado. |
| `email`              | `Mail`                   | Correo electrónico del cliente. |
| `phone`              | `Telefono`               | Número de teléfono del cliente. |

---

## ⚠️ **Consideraciones Importantes**
1. **El `Codigo` debe ser único**  
   - Se debe generar de forma única en el sistema antes de enviar el cliente a Cegid.

2. **El `CIF` (NIF) es obligatorio**  
   - Si un cliente no tiene NIF, se debe validar con el cliente cómo manejar estos casos.

3. **Verificar los datos antes de enviarlos**  
   - No todos los clientes en Holded tienen dirección, teléfono o correo electrónico. Se recomienda validar antes de enviar.

4. **Clientes duplicados**  
   - Antes de crear un nuevo cliente, se debe comprobar si ya existe en Cegid Diez usando `GET /Clientes`.

---

## 🔹 **Adjuntar Documentos a una Factura en Cegid Diez**
Para adjuntar un documento (ejemplo: PDF) a una factura en Cegid Diez, es necesario enviarlo en **Base64**.

📌 **Endpoint en Cegid Diez:**  
`POST /api/facturas/upload`

### **📄 Parámetros requeridos**
| Parámetro         | Tipo    | Obligatorio | Descripción |
|------------------|--------|------------|-------------|
| `Ejercicio`      | string | ✅ Sí      | Año contable de la factura. |
| `Serie`         | string | ✅ Sí      | Serie de la factura. |
| `Documento`      | int    | ✅ Sí      | Número de factura en Cegid. |
| `NombreArchivo`  | string | ✅ Sí      | Nombre del archivo (ej. `factura_12345.pdf`). |
| `Archivo`       | string | ✅ Sí      | Documento en **Base64**. |

### **📌 Ejemplo de JSON a enviar**
```json
{
  "Ejercicio": "2025",
  "Serie": "A",
  "Documento": 12345,
  "NombreArchivo": "factura_12345.pdf",
  "Archivo": "JVBERi0xLjUKJe... (contenido en Base64)"
}


