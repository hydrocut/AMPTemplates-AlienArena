#!/bin/bash
# installer-alienarena.sh - pose par le template AMP TeamKit (recree a chaque Update).
# Installe ou met a jour le serveur dedie d'Alien Arena (alienarena-ded) de la DERNIERE
# version publiee sur github.com/alienarena/alienarena, avec les donnees du jeu.
# Argument : le dossier de l'instance (FullBaseDir cote AMP).
#
# Pourquoi compiler : COR Entertainment ne publie aucun binaire Linux (unix_dist/INSTALL :
# "there is no pre-built executable"). Le serveur dedie seul (--disable-client) ne demande
# que gcc, make, pkg-config et zlib : environ 1 minute de compilation.
# Pourquoi tout le dossier data1 : le serveur lit les cartes (.bsp), mais aussi les modeles
# des joueurs (.iqm, zones de touche), les fichiers de collision des terrains
# (maps/meshes/...), les bots (botinfo/) et teste data1/pics/colormap.pcx au demarrage.
# Seules les sources des cartes (data1/maps/mapsrc, 176 Mo) et les outils Windows sont
# laisses de cote.
set -e
cd "$1"
DEPOT=alienarena/alienarena
# A changer si la facon d'installer change : force une reinstallation au prochain Update.
CORRECTIF=1
ICI="$PWD"
JEU="$ICI/jeu"
TRAVAIL="$ICI/.installation"
export LANG=C.UTF-8 LC_ALL=C.UTF-8

for outil in curl tar gzip gcc make pkg-config strip nproc; do
  if ! command -v "$outil" >/dev/null 2>&1; then
    echo "ERREUR : l'outil $outil manque. Cette instance doit tourner en conteneur : les outils de compilation sont installes par ExtraContainerPackages."
    exit 1
  fi
done

# --- Quelle version ? La derniere publiee (releases/latest de GitHub) ---
TAG=$(curl -fsSL --retry 3 -H 'Accept: application/vnd.github+json' "https://api.github.com/repos/$DEPOT/releases/latest" \
  | grep -o '"tag_name": *"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/') || TAG=""
if ! [[ "$TAG" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]]; then
  if [ -x "$JEU/alienarena-ded" ]; then
    echo "ATTENTION : GitHub ne repond pas (ou limite les demandes) : on garde la version installee ($(cut -d' ' -f1 "$JEU/.version" 2>/dev/null)). Relance Update plus tard."
    exit 0
  fi
  echo "ERREUR : impossible de connaitre la derniere version d'Alien Arena (api.github.com). Relance Update dans quelques minutes."
  exit 1
fi
MARQUE="$TAG teamkit-$CORRECTIF"

if [ -x "$JEU/alienarena-ded" ] && [ -f "$JEU/data1/pics/colormap.pcx" ] && [ "$(cat "$JEU/.version" 2>/dev/null)" = "$MARQUE" ]; then
  echo "TeamKit : Alien Arena $TAG est deja installe : rien a faire."
  exit 0
fi

# Place : environ 1,7 Go pour la nouvelle version, plus l'ancienne pendant le changement.
LIBRE=$(df -Pm . | awk 'NR==2 {print $4}')
if [[ "$LIBRE" =~ ^[0-9]+$ ]] && [ "$LIBRE" -lt 2000 ]; then
  echo "ERREUR : il reste $LIBRE Mo sur le disque de l'instance ; l'installation en demande environ 2 000."
  exit 1
fi

rm -rf "$TRAVAIL"
mkdir -p "$TRAVAIL/source"
echo "TeamKit : Alien Arena est un jeu libre de COR Entertainment : code sous licence GPL 2 (ou plus recente), donnees du jeu redistribuables seulement dans leur ensemble et pour Alien Arena (voir README et unix_dist/COPYING)."
echo "TeamKit : telechargement d'Alien Arena $TAG depuis github.com/$DEPOT (environ 1,2 Go, une a deux minutes)..."
(
  while sleep 15; do
    echo "TeamKit : telechargement en cours, $(du -sm "$TRAVAIL/source" 2>/dev/null | cut -f1) Mo extraits sur environ 1 650."
  done
) &
SUIVI=$!
set +e
curl -fsSL --retry 3 "https://codeload.github.com/$DEPOT/tar.gz/refs/tags/$TAG" \
  | tar -xz -C "$TRAVAIL/source" --strip-components=1 \
      --exclude='*/data1/maps/mapsrc' --exclude='*/Tools' --exclude='*/steam' --exclude='*/lib_zipfiles' \
      --exclude='*/vs2010' --exclude='*/flatpak' --exclude='*/source/win32' --exclude='*.exe' --exclude='*.dll'
CODES=("${PIPESTATUS[@]}")
set -e
kill "$SUIVI" 2>/dev/null || true
wait "$SUIVI" 2>/dev/null || true
if [ "${CODES[0]}" != 0 ] || [ "${CODES[1]}" != 0 ]; then
  rm -rf "$TRAVAIL"
  echo "ERREUR : telechargement ou extraction interrompu (curl ${CODES[0]}, tar ${CODES[1]}). Relance Update."
  exit 1
fi
cd "$TRAVAIL/source"
grep -q "AC_INIT(\[alienarena\],\[$TAG\]" configure.ac \
  || { echo "ERREUR : la source telechargee n'est pas celle de la version $TAG (configure.ac)."; exit 1; }
[ -f data1/pics/colormap.pcx ] && ls data1/maps/*.bsp >/dev/null 2>&1 && [ -d data1/botinfo ] && [ -d arena ] \
  || { echo "ERREUR : donnees du jeu incompletes dans l'archive (data1/pics, data1/maps, data1/botinfo, arena)."; exit 1; }

# --- Compilation du serveur dedie seul (pas le jeu : ni OpenGL, ni son, ni X11) ---
COEURS=$(nproc 2>/dev/null || echo 1)
[ "$COEURS" -gt 4 ] && COEURS=4
echo "TeamKit : configuration de la compilation (serveur dedie seul)..."
./configure --disable-client --without-data1pkg --disable-doc-install --disable-icons-install > ../configure.log 2>&1 \
  || { tail -n 30 ../configure.log; echo "ERREUR : la configuration a echoue (journal ci-dessus)."; exit 1; }
echo "TeamKit : compilation de alienarena-ded $TAG ($COEURS a la fois, environ une minute)..."
# Seulement la cible du serveur : "make" tout court compilerait aussi le moteur physique
# du jeu (ODE, en C++), inutile au serveur.
make -C source -j "$COEURS" alienarena-ded > ../make.log 2>&1 \
  || { grep -E -i 'error|erreur' ../make.log | tail -n 20; echo "ERREUR : la compilation a echoue (lignes ci-dessus)."; exit 1; }
[ -x source/alienarena-ded ] || { echo "ERREUR : source/alienarena-ded absent apres la compilation."; exit 1; }
strip source/alienarena-ded 2>/dev/null || true

# --- Mise en place : jeu/ = binaire + data1/ + arena/ (le serveur tourne "en place") ---
rm -rf "$JEU.nouveau"
mkdir -p "$JEU.nouveau"
mv data1 arena "$JEU.nouveau/"
cp source/alienarena-ded "$JEU.nouveau/"
mkdir -p "$JEU.nouveau/licences"
for f in unix_dist/COPYING unix_dist/GPLv2 unix_dist/README docs/license.txt; do
  [ -f "$f" ] && cp "$f" "$JEU.nouveau/licences/" || true
done
echo "$MARQUE" > "$JEU.nouveau/.version"
cd "$ICI"
rm -rf "$JEU"
mv "$JEU.nouveau" "$JEU"
rm -rf "$TRAVAIL"
CARTES=$(ls "$JEU"/data1/maps/*.bsp | wc -l)
echo "TeamKit : Alien Arena $TAG installe ($CARTES cartes officielles, $(du -sm "$JEU" | cut -f1) Mo)."
