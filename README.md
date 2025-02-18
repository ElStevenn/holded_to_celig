## DOCUMENTACIÓN

### Descripción
Este proyecto es una aplicación que permite obtener datos de una factura de Holded y de un contacto de Celig.


### Documentación API de Holded

 - Obtener listado de facturas (documentos)
```bash
    https://developers.holded.com/reference/list-documents-1
```

 - Detalle de una factura (documento)
 ```bash
    https://developers.holded.com/reference/getdocument-1
 ```

 - Detalle del contacto / listarlo
```bash
    https://developers.holded.com/reference/getcontact-1
    https://developers.holded.com/reference/list-contacts-1
```


#### Documentación de API de Celig
 - Datos de facturas
```bash
https://apirec.diezsoftware.com/swagger/index.html
```


### Datos de una factura
 - Datos del emisor (contract):
     - Numero de identificación fiscal (NIF, CIF, DNI, RFC) 
     - Nombre o Razon Social
     - Dirección
     - Teléfono | Correo electrónico (opcional)
 - Datos del Receptor 