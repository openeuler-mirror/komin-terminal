"""httpx client assembly for the AI backend.

Builds a fully configured :class:`httpx.Client` from a
:class:`komin_terminal.config.schema.BackendConfig`: base URL, timeouts,
headers, proxy and TLS material.
"""

from __future__ import annotations

import ssl

import httpx

from komin_terminal.config.schema import BackendConfig, TlsConfig
from komin_terminal.constants import DEFAULT_USER_AGENT


class HttpSession:
    """Assemble ``httpx`` clients from backend configuration."""

    def __init__(self, backend: BackendConfig) -> None:
        """Initialize the session with the backend settings.

        Args:
            backend: Backend connection settings.
        """
        self._backend = backend

    def create_client(self) -> httpx.Client:
        """Assemble a configured :class:`httpx.Client`.

        The client is configured with:

        - ``base_url`` and ``timeout`` from the backend settings;
        - an ``Authorization: Bearer <api_key>`` header, ``User-Agent`` and
          every ``extra_headers`` entry;
        - separate proxy transports for ``http://`` and ``https://`` when
          configured;
        - TLS: when ``tls`` is set, ``verify`` is an ``ssl.SSLContext``
          loaded with the CA bundle and, when both client certificate and
          key are provided, the client chain (mTLS).

        Returns:
            A fresh, fully configured client.
        """
        headers: dict[str, str] = {"User-Agent": DEFAULT_USER_AGENT}
        headers.update(self._backend.extra_headers)
        headers["Authorization"] = f"Bearer {self._backend.api_key}"

        timeout = httpx.Timeout(self._backend.timeout)
        verify: bool | ssl.SSLContext = True
        tls = self._backend.tls
        if tls is not None:
            verify = self._build_tls_context(tls)

        mounts = self._build_proxy_mounts()
        if mounts is not None:
            return httpx.Client(
                base_url=self._backend.url,
                timeout=timeout,
                headers=headers,
                verify=verify,
                mounts=mounts,
            )
        return httpx.Client(
            base_url=self._backend.url,
            timeout=timeout,
            headers=headers,
            verify=verify,
        )

    def _build_proxy_mounts(self) -> dict[str, httpx.HTTPTransport] | None:
        """Build per-scheme proxy transports from the backend proxy settings.

        Returns:
            A mapping of scheme prefix to transport, or ``None`` when no
            proxy is configured.
        """
        proxy = self._backend.proxy
        if proxy is None or (proxy.http is None and proxy.https is None):
            return None
        mounts: dict[str, httpx.HTTPTransport] = {}
        if proxy.http is not None:
            mounts["http://"] = httpx.HTTPTransport(proxy=proxy.http)
        if proxy.https is not None:
            mounts["https://"] = httpx.HTTPTransport(proxy=proxy.https)
        return mounts

    @staticmethod
    def _build_tls_context(tls: TlsConfig) -> ssl.SSLContext:
        """Build the TLS context for the backend connection.

        The context verifies against the CA bundle when provided and loads
        the client certificate chain when both certificate and key are set.
        httpx 0.28 drops the ``cert`` parameter when ``verify`` is a string
        (early return in ``create_ssl_context``), so the chain is loaded into
        the context directly to make mTLS actually effective.

        Args:
            tls: TLS configuration.

        Returns:
            A configured ``ssl.SSLContext``.
        """
        if tls.ca_bundle is not None:
            context = ssl.create_default_context(cafile=str(tls.ca_bundle))
        else:
            context = ssl.create_default_context()
        if tls.client_cert is not None and tls.client_key is not None:
            context.load_cert_chain(str(tls.client_cert), str(tls.client_key))
        return context


__all__ = ["HttpSession"]
