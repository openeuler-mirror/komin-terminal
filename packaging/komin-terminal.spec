%global srcname komin-terminal
# Normalized D-Bus vendor segment: %{_vendor} lowercased (openEuler -> openeuler).
# Must stay in sync with scripts/prepare_release.py normalization.
%global komin_vendor %(echo "%{_vendor}" | tr "[:upper:]" "[:lower:]")

Name:           %{srcname}
Version:        1.0.0
Release:        1%{?dist}
Summary:        AI-driven command line assistant for Linux system administration
License:        Apache-2.0
URL:            https://atomgit.com/openeuler/%{srcname}
Source0:        %{srcname}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3 >= 3.11
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools >= 68
BuildRequires:  python3-wheel
BuildRequires:  python3-build
BuildRequires:  python3-pip
# check-stage dependencies (offline test suite)
BuildRequires:  python3-pytest
BuildRequires:  python3-dasbus
BuildRequires:  python3-gobject
BuildRequires:  python3-httpx
BuildRequires:  python3-sqlalchemy
BuildRequires:  python3-pyyaml
BuildRequires:  python3-markdown

Requires:       python3 >= 3.11
Requires:       python3-dasbus
# openEuler/Fedora ship PyGObject as python3-gobject (not python3-pygobject)
Requires:       python3-gobject
Requires:       python3-httpx
Requires:       python3-sqlalchemy >= 1.4.45
Requires:       python3-pyyaml
Requires:       python3-markdown

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
Systemd service units, D-Bus policy and activation files, and example
configuration for komin-terminal. (SELinux policy sources ship in the
source tree; RPM packaging of compiled policy is future work.)

# ── Sub-package: help (documentation) ─────────────────────────────────
%package help
Summary:        Documentation for komin-terminal
BuildArch:      noarch
Requires:       %{srcname} = %{version}-%{release}

%description help
Man pages for komin-terminal.

# ── Prep ────────────────────────────────────────────────────────────────
%prep
%autosetup -n %{srcname}-%{version}

# ── Build ───────────────────────────────────────────────────────────────
%build
# Bake the release vendor into constants.py so the wheel ships a client and
# daemon that both default to the distribution D-Bus vendor. The pristine
# source is restored afterwards so the check stage still validates the
# development default. (Deployment-file substitution happens separately on a
# staging copy in the install stage.)
cp komin_terminal/constants.py ./constants.py.rpmbak
python3 scripts/prepare_release.py --root komin_terminal --vendor %{_vendor}
python3 -m build --wheel --no-isolation
mv ./constants.py.rpmbak komin_terminal/constants.py

# ── Check ───────────────────────────────────────────────────────────────
%check
# Offline test suite.
python3 -m pytest tests/ -v

# ── Install ─────────────────────────────────────────────────────────────
%install
# Work on a staging copy of the release data so the BUILD tree keeps the
# pristine {vendor} templates that the check stage validates.
staging=%{_builddir}/staging-release
rm -rf "$staging"
cp -a data/release "$staging"
python3 scripts/prepare_release.py --root "$staging" --vendor %{_vendor}
# File names are not content-substituted: rename the D-Bus deployment files
# so their names carry the real vendor (required for D-Bus service activation).
pushd "$staging/dbus"
for f in *; do
    newname=$(echo "$f" | sed "s/{vendor}/%{komin_vendor}/")
    if [ "$f" != "$newname" ]; then
        mv "$f" "$newname"
    fi
done
popd

python3 -m pip install --no-deps --force-reinstall --root=%{buildroot} dist/*.whl

# Install vendor-substituted release files from the staging copy
install -d %{buildroot}%{_sysconfdir}/komin
install -m 0644 "$staging"/xdg/config.yaml %{buildroot}%{_sysconfdir}/komin/config.yaml

install -d %{buildroot}%{_unitdir}
install -m 0644 "$staging"/systemd/komind.service %{buildroot}%{_unitdir}/komind.service
install -d %{buildroot}%{_tmpfilesdir}
install -m 0644 "$staging"/systemd/komind.tmpfiles.conf %{buildroot}%{_tmpfilesdir}/komind.conf

install -d %{buildroot}%{_datadir}/dbus-1/system-services
install -m 0644 "$staging"/dbus/com.*.komin.chat.service %{buildroot}%{_datadir}/dbus-1/system-services/
install -m 0644 "$staging"/dbus/com.*.komin.history.service %{buildroot}%{_datadir}/dbus-1/system-services/
install -m 0644 "$staging"/dbus/com.*.komin.user.service %{buildroot}%{_datadir}/dbus-1/system-services/

install -d %{buildroot}%{_datadir}/dbus-1/system.d
install -m 0644 "$staging"/dbus/com.*.komin.conf %{buildroot}%{_datadir}/dbus-1/system.d/

install -d %{buildroot}%{_mandir}/man1
install -m 0644 "$staging"/man/km.1 %{buildroot}%{_mandir}/man1/km.1
install -d %{buildroot}%{_mandir}/man8
install -m 0644 "$staging"/man/komind.8 %{buildroot}%{_mandir}/man8/komind.8

rm -rf "$staging"

# ── Post-install (data subpackage) ─────────────────────────────────────
# Scriptlets live here, not in the main package: the tmpfiles drop-in,
# systemd unit and D-Bus policy they act on are all shipped by this
# subpackage, which installs after the main package. %posttrans runs
# after the whole transaction, so the drop-in is guaranteed to exist.
%posttrans data
systemd-tmpfiles --create %{_tmpfilesdir}/komind.conf || :
systemctl daemon-reload >/dev/null 2>&1 || :
systemctl reload dbus.service >/dev/null 2>&1 || :

# ── Post-uninstall (data subpackage) ───────────────────────────────────
%postun data
if [ $1 -eq 0 ]; then
    # Package removal (not upgrade)
    systemctl daemon-reload >/dev/null 2>&1 || :
    systemctl reload dbus.service >/dev/null 2>&1 || :
fi

# ── Files: main package ────────────────────────────────────────────────
%files
%license LICENSE
%{python3_sitelib}/komin_terminal/
%{python3_sitelib}/komin_terminal-%{version}.dist-info/
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

# ── Files: help sub-package ───────────────────────────────────────────
%files help
%{_mandir}/man1/km.1*
%{_mandir}/man8/komind.8*
