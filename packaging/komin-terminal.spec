%global srcname komin-terminal

Name:           %{srcname}
Version:        1.0.0
Release:        1%{?dist}
Summary:        AI-driven command line assistant for Linux system administration
License:        Apache-2.0
URL:            https://github.com/komin/%{srcname}
Source0:        %{srcname}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3 >= 3.11
BuildRequires:  python3-setuptools >= 68
BuildRequires:  python3-wheel

Requires:       python3 >= 3.11
Requires:       python3-dasbus
Requires:       python3-pygobject
Requires:       python3-httpx
Requires:       python3-sqlalchemy
Requires:       python3-pyyaml

%description
Komin-Terminal is an AI-driven command line assistant for Linux system
administrators. It provides a CLI (km/komin) and a D-Bus daemon (komind)
for streaming AI responses, session management, and terminal output capture.

# ── Sub-package: data (deployment files) ──────────────────────────────
%package data
Summary:        Deployment files for komin-terminal
BuildArch:      noarch
Requires:       %{srcname} = %{version}-%{release}

%description data
Systemd service units, D-Bus activation files, SELinux policy, man pages,
and example configuration for komin-terminal.

# ── Sub-package: doc (documentation) ──────────────────────────────────
%package doc
Summary:        Documentation for komin-terminal
BuildArch:      noarch
Requires:       %{srcname} = %{version}-%{release}

%description doc
Man pages and (in a future phase) Sphinx-built documentation for
komin-terminal.

# ── Prep ────────────────────────────────────────────────────────────────
%prep
%autosetup -n %{srcname}-%{version}

# ── Build ───────────────────────────────────────────────────────────────
%build
# Replace {vendor} placeholders with the RPM vendor macro.
python3 scripts/prepare_release.py --vendor %{_vendor}
python3 -m build --wheel --no-isolation

# ── Check ───────────────────────────────────────────────────────────────
%check
make test

# ── Install ─────────────────────────────────────────────────────────────
%install
python3 -m pip install --no-deps --root=%{buildroot} dist/*.whl

# Install data/release files
install -d %{buildroot}%{_sysconfdir}/komin
install -m 0644 data/release/xdg/config.yaml %{buildroot}%{_sysconfdir}/komin/config.yaml

install -d %{buildroot}%{_unitdir}
install -m 0644 data/release/systemd/komind.service %{buildroot}%{_unitdir}/komind.service
install -m 0644 data/release/systemd/komind.tmpfiles.conf %{buildroot}%{_tmpfilesdir}/komind.conf

install -d %{buildroot}%{_datadir}/dbus-1/system-services
install -m 0644 data/release/dbus/com.*.komin.chat.service %{buildroot}%{_datadir}/dbus-1/system-services/
install -m 0644 data/release/dbus/com.*.komin.history.service %{buildroot}%{_datadir}/dbus-1/system-services/
install -m 0644 data/release/dbus/com.*.komin.user.service %{buildroot}%{_datadir}/dbus-1/system-services/

install -d %{buildroot}%{_datadir}/dbus-1/system.d
install -m 0644 data/release/dbus/com.*.komin.conf %{buildroot}%{_datadir}/dbus-1/system.d/

install -d %{buildroot}%{_mandir}/man1
install -m 0644 data/release/man/km.1 %{buildroot}%{_mandir}/man1/km.1
install -d %{buildroot}%{_mandir}/man8
install -m 0644 data/release/man/komind.8 %{buildroot}%{_mandir}/man8/komind.8

# ── Post-install ────────────────────────────────────────────────────────
%post
# Enable tmpfiles for /var/lib/komin
systemd-tmpfiles --create %{_tmpfilesdir}/komind.conf || :
# Reload D-Bus configuration
busctl daemon-reload || :

# ── Post-uninstall ──────────────────────────────────────────────────────
%postun
if [ $1 -eq 0 ]; then
    # Package removal (not upgrade)
    busctl daemon-reload || :
fi

# ── Files: main package ────────────────────────────────────────────────
%files
%license LICENSE
%{python3_sitelib}/komin_terminal/
%{python3_sitelib}/%{srcname}-%{version}.dist-info/
%{_bindir}/km
%{_bindir}/komin
%{_bindir}/komind

# ── Files: data sub-package ────────────────────────────────────────────
%files data
%config(noreplace) %{_sysconfdir}/komin/config.yaml
%{_unitdir}/komind.service
%{_tmpfilesdir}/komind.conf
%{_datadir}/dbus-1/system-services/com.*.komin.chat.service
%{_datadir}/dbus-1/system-services/com.*.komin.history.service
%{_datadir}/dbus-1/system-services/com.*.komin.user.service
%{_datadir}/dbus-1/system.d/com.*.komin.conf

# ── Files: doc sub-package ─────────────────────────────────────────────
%files doc
%{_mandir}/man1/km.1*
%{_mandir}/man8/komind.8*
