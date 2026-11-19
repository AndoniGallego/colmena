# Entornos locales desde la PC

> Esta regla rige cuando la sesión corre en una terminal de Colmena (COLMENA_TERMINAL=1). Si no sabés, aplicala.

<!-- propósito: Si estás en la PC, la sesión te manda a la ventana Entornos de Colmena en vez de a localhost de la notebook. -->

Ando puede estar en la PC Windows y no frente a la notebook. Las tiendas y servicios corren en Docker en la notebook, escuchando en 127.0.0.1: desde el navegador de la PC, `localhost` no llega sin un túnel SSH.

Cuando Ando tenga que ver o probar algo de un entorno local (tienda, panel, mailhog, mocks...), no lo mandes al navegador de la notebook. Sugerile abrirlo desde la ventana **Entornos** de la app de Windows de Colmena (bandeja → Entornos, o el menú de la web) con el botón **Abrir** del entorno. Eso arma el túnel y abre la página en su navegador, con la misma URL `http://localhost:<puerto>`.

Si no tiene la app a mano, el túnel manual desde la PC, con los puertos del entorno:

```
ssh -N -L 8080:localhost:8080 cc@<IP de la notebook en la red de casa>
```

- Solo funciona desde la red de casa. Por Tailscale el SSH está cerrado a propósito: no lo propongas.
- Los puertos salen de `docker compose ps` (o `docker ps`) en la notebook: los publicados del entorno.

Si Ando está fuera de casa, decile que el túnel no está disponible y ofrecé que la sesión haga la prueba sola con el navegador de la notebook, y le muestre el resultado en un bloque `pruebas`.

Nunca propongas abrir puertos a la red, `tailscale funnel` ni tocar la configuración de SSH.
