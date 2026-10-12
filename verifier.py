# -*- coding: utf-8 -*-
"""
Contrôle du template avant de le pousser (même rôle que ceux d'Urban Terror et de ClassiCube).

    python verifier.py

1. tous les JSON se parsent ;
2. le .kvp : fichiers inclus, Ref du port, bloc Console.* / Limits.* complet, console d'AMP
   sur l'entrée du serveur (STDIO), arrêt par « quit », conteneur + paquets de compilation,
   identifiants neufs (AppConfigId et id du manifest absents des autres templates TeamKit) ;
3. chaque réglage exposé dans AMP est écrit dans scripts/AMP_reglages-alienarena.txt (rendu
   par AMP en reglages-alienarena.txt) et lu par le lanceur, et inversement, sauf « Joueurs
   maximum » : AMP le passe sur la ligne de commande ({{$MaxUsers}}) ;
4. les choix, bornes et valeurs par défaut d'AMP sont ceux du lanceur ;
5. les fichiers téléchargés à l'Update existent dans scripts/, à l'URL du dépôt du manifest,
   et la dernière étape lance bien l'installeur ;
6. les scripts : LF, ASCII, sans {{, `bash -n` si bash est là, pas d'apostrophe dans le pont ;
7. aller-retour : on rend le modèle comme AMP (remplacement brut) avec les valeurs par défaut
   puis des valeurs piégées (accents, guillemets, point-virgule, antislash, $, //, vide), on
   passe le tout dans la vraie partie Python du lanceur (fausse instance avec de fausses
   cartes), puis on relit amp-teamkit.cfg comme le moteur (Cbuf_Execute, COM_Parse, $cvar) :
   chaque valeur doit arriver entière, en ASCII, sans " ; ni \\ ;
8. le pont (liste des joueurs, chat, RCON masqué, ligne « prêt ») sur les vraies lignes
   d'Alien Arena 7.72.3 relevées le 11 oct. 2026 dans des conteneurs jetables avec deux vrais
   clients (arrivée, bots, chat, renommage silencieux, exclusion, départ, changement de carte) ;
9. les regex de console sur ces lignes, avec et sans le FilterMatchRegex appliqué avant.
"""
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
NOM = 'alienarena'
MODELE = 'scripts/AMP_reglages-alienarena.txt'
LANCEUR = 'scripts/lancer-alienarena.sh'
INSTALLEUR = 'scripts/installer-alienarena.sh'
soucis = []


def lire(nom, binaire=False):
    with open(os.path.join(ICI, nom), 'rb') as f:
        brut = f.read()
    return brut if binaire else brut.decode('utf-8')


def ok(quoi, detail):
    print('ok   %-26s %s' % (quoi, detail))


def py(motif):
    # AMP est en C# : (?<nom>...) ; Python veut (?P<nom>...)
    return re.compile(motif.replace('(?<', '(?P<'))


# ── 1. JSON ──────────────────────────────────────────────────────────────────
data = {}
for nom in ('manifest.json', NOM + 'config.json', NOM + 'metaconfig.json', NOM + 'ports.json', NOM + 'updates.json'):
    try:
        data[nom] = json.loads(lire(nom))
        ok(nom, 'JSON valide')
    except Exception as e:
        soucis.append('%s : JSON invalide (%s)' % (nom, e))
if soucis:
    print('\n'.join('NON  ' + s for s in soucis))
    sys.exit(1)
config = data[NOM + 'config.json']
updates = data[NOM + 'updates.json']
ports = data[NOM + 'ports.json']
lanceur = lire(LANCEUR)
installeur = lire(INSTALLEUR)
modele = lire(MODELE)

# ── 2. kvp ───────────────────────────────────────────────────────────────────
kvp = lire(NOM + '.kvp')
cles = dict(l.split('=', 1) for l in kvp.splitlines() if '=' in l)
for ref in re.findall(r'@IncludeJson\[([^\]]+)\]', kvp):
    if not os.path.isfile(os.path.join(ICI, ref)):
        soucis.append('@IncludeJson[%s] : fichier absent' % ref)
for cle in ('Meta.ConfigManifest', 'Meta.MetaConfigManifest'):
    if not os.path.isfile(os.path.join(ICI, cles.get(cle, '?'))):
        soucis.append('%s pointe sur un fichier absent' % cle)
refs = {p['Ref'] for p in ports}
if cles.get('App.PrimaryApplicationPortRef') not in refs:
    soucis.append('PrimaryApplicationPortRef ne correspond à aucun port')
cmd = cles.get('App.CommandLineArgs', '')
for r in re.findall(r'\{\{\$(\w+)\}\}', cmd):
    if r not in refs and r not in ('FullBaseDir', 'MaxUsers'):
        soucis.append('{{$%s}} : aucun port ne porte ce Ref' % r)
if cmd != '"{{$FullBaseDir}}lancer-alienarena.sh" {{$%s}} {{$MaxUsers}}' % cles.get('App.PrimaryApplicationPortRef'):
    soucis.append('ligne de commande inattendue : %s' % cmd)
if [(p['Port'], p['Protocol']) for p in ports] != [(27910, 'UDP')]:
    soucis.append('Alien Arena n’utilise qu’un port, 27910 en UDP (PORT_SERVER)')
ok('ports', ', '.join('%s %s/%s' % (p['Ref'], p['Port'], p['Protocol']) for p in ports))
ATTENDUES = ['App.SupportsUniversalSleep', 'App.WakeupMode', 'App.ApplicationReadyMode', 'Console.FilterMatchRegex',
             'Console.FilterMatchReplacement', 'Console.ThrowawayMessageRegex', 'Console.AppReadyRegex',
             'Console.UserJoinRegex', 'Console.UserLeaveRegex', 'Console.UserChatRegex', 'Console.UpdateAvailableRegex',
             'Console.PreConnectRegex', 'Console.ConnectIPRegex', 'Console.MetricsRegex', 'Console.HideFromConsoleRegex',
             'Console.SuppressLogAtStart', 'Console.UserActions', 'Limits.SleepMode', 'Limits.SleepOnStart',
             'Limits.SleepDelayMinutes', 'Limits.DozeDelay', 'Limits.AutoRetryCount', 'Limits.SleepStartThresholdSeconds']
absentes = [c for c in ATTENDUES if c not in cles]
if absentes:
    soucis.append('clés absentes du .kvp : ' + ', '.join(absentes))
else:
    ok('kvp complet', 'les %d clés Console/Limits sont là' % len(ATTENDUES))
ATTENDU_KVP = {
    'App.ApplicationReadyMode': 'RegexMatch',
    'App.HasWriteableConsole': 'True',        # la console d'AMP va au serveur par le pont
    'App.AdminMethod': 'STDIO',
    'App.ExitMethod': 'String',               # « quit » : ShutdownGame, code 0 (essai)
    'App.ExitString': 'quit',
    'App.ExecutableLinux': '/bin/bash',
    'Meta.ContainerPolicy': 'Required',
    'Meta.SpecificDockerImage': 'cubecoders/ampbase:debian',
    'App.MaxUsers': '16',
}
for cle, val in ATTENDU_KVP.items():
    if cles.get(cle) != val:
        soucis.append('%s devrait valoir %s (vaut %r)' % (cle, val, cles.get(cle)))
if not cles.get('Console.AppReadyRegex'):
    soucis.append('RegexMatch sans AppReadyRegex : l’instance ne serait jamais déclarée prête')
PAQUETS = ['gcc', 'make', 'libc6-dev', 'pkg-config', 'zlib1g-dev']
if json.loads(cles.get('Meta.ExtraContainerPackages', '[]')) != PAQUETS:
    soucis.append('ExtraContainerPackages doit être %s (compilation du serveur seul)' % PAQUETS)
for outil in ('gcc', 'make', 'pkg-config'):
    if not re.search(r'for outil in [^;]*\b%s\b' % re.escape(outil), installeur):
        soucis.append('l’installeur doit vérifier la présence de %s' % outil)
if cles.get('Meta.URL') != data['manifest.json']['url']:
    soucis.append('Meta.URL et manifest.json ne désignent pas le même dépôt')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}')
mes_ids = {cles.get('Meta.AppConfigId', ''), data['manifest.json'].get('id', '')}
if len(mes_ids) != 2 or not all(UUID.fullmatch(i) for i in mes_ids):
    soucis.append('AppConfigId et id du manifest : deux UUID v4 différents')
autres = 0
for chemin in glob.glob(os.path.join(ICI, '..', 'AMPTemplates-*', '*')):
    if os.path.dirname(os.path.abspath(chemin)) == ICI or not chemin.endswith(('.kvp', 'manifest.json')):
        continue
    try:
        contenu = open(chemin, encoding='utf-8', errors='replace').read()
    except OSError:
        continue
    autres += 1
    for i in mes_ids:
        if i and i in contenu:
            soucis.append('identifiant %s déjà utilisé par %s' % (i, chemin))
ok('kvp', 'STDIO, arrêt par quit, conteneur + %d paquets, identifiants neufs (%d fichiers comparés)'
   % (len(PAQUETS), autres))

# ── 3. réglages <-> modèle <-> lanceur ───────────────────────────────────────
par_param = {}
for c in config:
    p = c['ParamFieldName']
    if p in par_param:
        soucis.append('réglage en double : %s' % p)
    par_param[p] = c
    attendu = 'maxclients' if c['FieldName'] == '$MaxUsers' else c['FieldName']
    if p != attendu:
        soucis.append('%s : ParamFieldName %s inattendu' % (c['FieldName'], p))
lignes_modele = [l for l in modele.splitlines() if l and not l.startswith('#')]
dans_modele = {}
for l in lignes_modele:
    m = re.fullmatch(r'([a-z_]+)=\{\{(\$?\w+)\}\}', l)
    if not m:
        soucis.append('ligne du modèle inattendue : %s' % l)
        continue
    dans_modele[m.group(1)] = m.group(2)
if 'maxclients' in dans_modele or '{{$' in modele:
    soucis.append('%s : ni ligne maxclients ni {{$...}} (AMP ne les remplace pas dans ce fichier)' % MODELE)
for p, c in par_param.items():
    if p == 'maxclients':
        continue
    if dans_modele.get(p) != c['FieldName']:
        soucis.append('%s : attendu « %s={{%s}} » dans %s' % (p, p, c['FieldName'], MODELE))
for p in set(dans_modele) - set(par_param):
    soucis.append('%s dans %s mais aucun réglage AMP' % (p, MODELE))
LU = re.compile(r"""(?:R\.get|texte|nombre|choix|case|mot_de_passe)\('([a-z_]+)'""")
lus = set(LU.findall(lanceur))
m = re.search(r"^MUTATEURS = \[([^\]]*)\]", lanceur, re.M)
MUTATEURS = re.findall(r"'([a-z_]+)'", m.group(1)) if m else []
lus |= set(MUTATEURS)
if lus != set(dans_modele) | {'maxclients'}:
    soucis.append('clés du modèle %s ≠ clés lues par le lanceur %s' % (sorted(dans_modele), sorted(lus)))
else:
    ok('correspondance', '%d réglages : AMP -> %s -> lanceur' % (len(par_param), os.path.basename(MODELE)))
meta = data[NOM + 'metaconfig.json'][0]
racine = cles['App.RootDir'].strip('./').strip('/')
if meta.get('ConfigType') != 'template' or meta.get('ConfigFileTemplate') != racine + '/AMP_reglages-alienarena.txt':
    soucis.append('metaconfig : ConfigFileTemplate devrait être %s/AMP_reglages-alienarena.txt' % racine)
if meta.get('ConfigFile') != 'reglages-alienarena.txt' or "'reglages-alienarena.txt'" not in lanceur:
    soucis.append('le fichier rendu par AMP (ConfigFile) n’est pas celui que lit le lanceur')
mu = par_param['maxclients']
if mu['FieldName'] != '$MaxUsers' or mu['DefaultValue'] != cles.get('App.MaxUsers'):
    soucis.append('Joueurs maximum : $MaxUsers, défaut égal à App.MaxUsers')
if par_param['hostname']['DefaultValue'] != '^4[^7FR^1] ^5TeamKit ^7- ^2Alien Arena':
    soucis.append('nom du serveur par défaut : ^4[^7FR^1] ^5TeamKit ^7- ^2Alien Arena')
d = par_param['motd']['DefaultValue']
if 'teamkit.fr' not in d or 'discord.gg/EuAjGMYPHY' not in d or any(ord(ch) > 127 for ch in d):
    soucis.append('message d’accueil par défaut : teamkit.fr, le Discord, sans accent (le jeu n’affiche que l’ASCII)')
for p in ('password', 'rcon_password'):
    if par_param[p]['InputType'] != 'password' or par_param[p]['DefaultValue'] != '':
        soucis.append('%s : champ masqué (password), vide par défaut' % p)
for c in config:
    if c['DisplayName'] == c['FieldName'] or not c['Description']:
        soucis.append('%s : libellé et description en français attendus' % c['FieldName'])

# ── 4. choix, bornes, défauts : AMP == lanceur ───────────────────────────────
for m in re.finditer(r"choix\('(\w+)', '([^']*)', (\[[^\]]*\]|ARMES_TOUTES)\)", lanceur):
    p, defaut, permis = m.group(1), m.group(2), set(re.findall(r"'([^']*)'", m.group(3)))
    if p == 'armes':
        permis |= set(re.findall(r"'([a-z_]+)'", re.search(r"^ARMES = \[([^\]]*)\]", lanceur, re.M).group(1)))
    c = par_param[p]
    proposes = set(c['EnumValues'].values()) if c['InputType'] == 'checkbox' else set(c['EnumValues'])
    if proposes != permis:
        soucis.append('%s : AMP propose %s, le lanceur accepte %s' % (p, sorted(proposes), sorted(permis)))
    if c['DefaultValue'] != defaut:
        soucis.append('%s : défaut AMP %r, défaut du lanceur %r' % (p, c['DefaultValue'], defaut))
for m in re.finditer(r"case\('(\w+)', '([01])'\)", lanceur):
    p, defaut = m.groups()
    c = par_param[p]
    if c['InputType'] != 'checkbox' or c['EnumValues'] != {'False': '0', 'True': '1'} or c['DefaultValue'] != defaut:
        soucis.append('%s : case à cocher 0/1, défaut %s attendu' % (p, defaut))
for p in MUTATEURS:
    c = par_param[p]
    if c['InputType'] != 'checkbox' or c['DefaultValue'] != '0' or c['EnumValues'] != {'False': '0', 'True': '1'}:
        soucis.append('%s : mutateur = case à cocher, décochée par défaut' % p)
if not re.search(r"mutateurs = \{m: case\(m, '0'\) for m in MUTATEURS\}", lanceur):
    soucis.append('les mutateurs doivent être lus par case(m, \'0\')')
for m in re.finditer(r"nombre\('(\w+)', (-?\d+), (-?\d+), (-?\d+)\)", lanceur):
    p, defaut, mini, maxi = m.groups()
    c = par_param[p]
    if (c['DefaultValue'], c.get('MinValue'), c.get('MaxValue')) != (defaut, mini, maxi):
        soucis.append('%s : AMP (%s, %s-%s) ≠ lanceur (%s, %s-%s)' % (
            p, c['DefaultValue'], c.get('MinValue'), c.get('MaxValue'), defaut, mini, maxi))
ok('choix et bornes', 'énumérations, cases, nombres et défauts identiques')

# ── 5. Update ────────────────────────────────────────────────────────────────
depot = data['manifest.json']['url'].replace('https://github.com/', '')
nos_fichiers = set()
for e in updates:
    if e['UpdateSource'] != 'FetchURL':
        continue
    attendu = 'https://raw.githubusercontent.com/%s/main/scripts/%s' % (depot, e['UpdateSourceArgs'])
    if e['UpdateSourceData'] != attendu:
        soucis.append('URL inattendue pour %s : %s' % (e['UpdateSourceArgs'], e['UpdateSourceData']))
    elif not os.path.isfile(os.path.join(ICI, 'scripts', e['UpdateSourceArgs'])):
        soucis.append('scripts/%s absent du dépôt' % e['UpdateSourceArgs'])
    nos_fichiers.add(e['UpdateSourceArgs'])
    if e.get('UpdateSourceTarget') != '{{$FullBaseDir}}' or e.get('OverwriteExistingFiles') is not True:
        soucis.append('%s : doit être réécrit dans {{$FullBaseDir}} à chaque Update' % e['UpdateSourceArgs'])
if nos_fichiers != {'AMP_reglages-alienarena.txt', 'lancer-alienarena.sh', 'installer-alienarena.sh'}:
    soucis.append('l’Update doit déposer les trois fichiers de scripts/')
dernier = updates[-1]
if (dernier['UpdateSource'], dernier['UpdateSourceData'], dernier['UpdateSourceArgs']) != \
        ('Executable', '/bin/bash', '"{{$FullBaseDir}}installer-alienarena.sh" "{{$FullBaseDir}}"') \
        or dernier.get('SkipOnFailure'):
    soucis.append('dernière étape : /bin/bash "{{$FullBaseDir}}installer-alienarena.sh" "{{$FullBaseDir}}", sans SkipOnFailure')
for besoin in ('https://api.github.com/repos/$DEPOT/releases/latest', 'https://codeload.github.com/$DEPOT/tar.gz/refs/tags/$TAG',
               '--disable-client --without-data1pkg', 'make -C source -j "$COEURS" alienarena-ded',
               "--exclude='*/data1/maps/mapsrc'", 'DEPOT=alienarena/alienarena', 'data1/pics/colormap.pcx'):
    if besoin not in installeur:
        soucis.append('installeur : %s absent' % besoin)
ok('Update', '%s, puis « installer-alienarena.sh »' % ', '.join(sorted(nos_fichiers)))

# ── 6. scripts ───────────────────────────────────────────────────────────────
for nom in (LANCEUR, INSTALLEUR, MODELE):
    brut = lire(nom, binaire=True)
    if b'\r' in brut:
        soucis.append('%s : fins de ligne Windows (CRLF)' % nom)
    if any(o > 127 for o in brut):
        soucis.append('%s : caractères non ASCII' % nom)
for nom, texte in ((LANCEUR, lanceur), (INSTALLEUR, installeur)):
    if '{{' in texte:
        soucis.append('%s contient {{ : AMP pourrait le remplacer' % nom)
    if 'eval ' in texte:
        soucis.append('%s : pas d’eval' % nom)
for besoin, pourquoi in [
    ('exec python3 -I -u -c "$PONT" "$PORT" "$JEU" "$BIN"', 'le pont remplace le lanceur (console et quit d’AMP)'),
    ('+exec amp-teamkit.cfg', 'config écrite par le lanceur'),
    ('export XDG_DATA_HOME="$DONNEES"', 'données du serveur dans l’instance'),
    ('+set sys_ansicolor 0', 'pas de couleurs ANSI dans la console d’AMP'),
    ('reglage[3] &= ~(termios.ECHO | termios.ECHONL)', 'pas d’écho des commandes'),
]:
    if besoin not in lanceur:
        soucis.append('lanceur : %s (%s)' % (besoin, pourquoi))
m = re.search(r"^PONT='\n(.*?)^'$", lanceur, re.S | re.M)
PONT = m.group(1) if m else None
if not PONT:
    soucis.append('programme PONT introuvable dans le lanceur')
elif "'" in PONT:
    soucis.append('PONT contient une apostrophe : elle fermerait la chaîne bash')
bash = None
for c in (r'C:\Program Files\Git\bin\bash.exe', '/bin/bash', shutil.which('bash')):
    if c and os.path.isfile(c) and 'system32' not in c.lower():
        bash = c
        break
if bash:
    for nom in (LANCEUR, INSTALLEUR):
        r = subprocess.run([bash, '-n', os.path.join(ICI, nom)], capture_output=True, text=True)
        if r.returncode:
            soucis.append('bash -n %s : %s' % (nom, r.stderr.strip()))
    ok('bash -n', '%s, %s' % (LANCEUR, INSTALLEUR))
else:
    print('--   bash -n                    pas de bash ici, syntaxe non vérifiée')

# ── 7. aller-retour AMP -> lanceur (partie Python) -> moteur ─────────────────
m = re.search(r"^python3 -I - \"\$ICI\" \"\$JOUEURS\" <<'PY'\n(.*?)^PY$", lanceur, re.S | re.M)
PREPARER = m.group(1) if m else None
if not PREPARER:
    soucis.append('partie Python du lanceur introuvable')
CARTES = ['dm-deathray', 'dm-babel', 'dm-turbo', 'ctf-frost', 'ctf-zion', 'tac-impact']
MAPS_LST = 'dm-deathray "Deathray Deluxe"\ndm-annihilation "Total Annihilation"\ndm-turbo "Turbocharger"\n' \
           'dm-babel "Tower of Babel"\nctf-frost "Frost Byte CTF"\ntac-impact "Deep Impact"\n0'


def rendre(valeurs):
    t = modele
    for c in config:
        t = t.replace('{{%s}}' % c['FieldName'], valeurs.get(c['ParamFieldName'], c['DefaultValue']))
    return t


def lire_cfg_comme_le_moteur(texte):
    """Cbuf_Execute (coupe sur ; hors guillemets et fin de ligne), Cmd_MacroExpandString ($cvar
    hors guillemets) puis COM_Parse (// hors guillemets = commentaire)."""
    commandes = []
    for ligne in texte.split('\n'):
        guillemets, debut = 0, 0
        for i, ch in enumerate(ligne + ';'):
            if ch == '"':
                guillemets += 1
            if (ch == ';' and not guillemets % 2) or i == len(ligne):
                commandes.append(ligne[debut:i])
                debut = i + 1
    vals, cmds = {}, []
    for c in commandes:
        dedans = False
        for ch in c:
            if ch == '"':
                dedans = not dedans
            elif ch == '$' and not dedans:
                vals.setdefault('__macro__', []).append(c)
        jetons, i = [], 0
        while i < len(c):
            if c[i] <= ' ':
                i += 1
            elif c.startswith('//', i):
                break
            elif c[i] == '"':
                j = c.find('"', i + 1)
                j = len(c) if j < 0 else j
                jetons.append(c[i + 1:j])
                i = j + 1
            else:
                j = i
                while j < len(c) and c[j] > ' ':
                    j += 1
                jetons.append(c[i:j])
                i = j
        if not jetons:
            continue
        cmds.append(jetons)
        if jetons[0] == 'set' and len(jetons) in (3, 4):
            vals[jetons[1]] = jetons[2]
            if len(jetons) == 4:
                vals[jetons[1] + '/drapeau'] = jetons[3]
        elif jetons[0] == 'set':
            vals[jetons[1]] = None              # valeur coupée en plusieurs jetons
        elif jetons[0] in ('map', 'exec', 'setmaster'):
            vals[jetons[0]] = jetons[1:]
    vals['__cmds__'] = cmds
    return vals


def preparer(valeurs, joueurs='16', avant=None):
    """Lance la vraie partie Python du lanceur dans une fausse instance."""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, 'jeu', 'data1', 'maps'))
        os.makedirs(os.path.join(tmp, 'jeu', 'arena', 'maps'))
        os.makedirs(os.path.join(tmp, 'donnees', 'cor-games', 'arena'))
        for c in CARTES:
            open(os.path.join(tmp, 'jeu', 'data1', 'maps', c + '.bsp'), 'wb').write(b'IBSP')
        open(os.path.join(tmp, 'jeu', 'arena', 'maps', 'shadowtest.bsp'), 'wb').write(b'IBSP')
        open(os.path.join(tmp, 'jeu', 'arena', 'maps.lst'), 'w').write(MAPS_LST)
        if avant:
            avant(tmp)
        with io.open(os.path.join(tmp, 'reglages-alienarena.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(rendre(valeurs))
        p = subprocess.run([sys.executable, '-I', '-', tmp, joueurs], input=PREPARER.encode('utf-8'),
                           capture_output=True, timeout=60)
        texte = p.stdout.decode('utf-8', 'replace') + p.stderr.decode('utf-8', 'replace')
        res = {'code': p.returncode, 'texte': texte}
        perso = os.path.join(tmp, 'donnees', 'cor-games', 'arena')
        cfg = os.path.join(perso, 'amp-teamkit.cfg')
        if os.path.isfile(cfg):
            res['cfg_brut'] = open(cfg, 'rb').read()
            res['cfg'] = lire_cfg_comme_le_moteur(res['cfg_brut'].decode('ascii'))
        for nom in ('amp-motd.txt', 'perso.cfg'):
            if os.path.isfile(os.path.join(perso, nom)):
                res[nom] = open(os.path.join(perso, nom), 'rb').read().decode('ascii')
        if os.path.isfile(os.path.join(tmp, 'cartes-disponibles.txt')):
            res['cartes'] = open(os.path.join(tmp, 'cartes-disponibles.txt')).read()
        return res


if PREPARER:
    defauts = {c['ParamFieldName']: c['DefaultValue'] for c in config}
    n = 0
    r = preparer({})
    n += 1
    if r['code'] != 0 or 'cfg' not in r:
        soucis.append('valeurs par défaut : le lanceur refuse\n%s' % r['texte'])
    else:
        v = r['cfg']
        if v.get('hostname') != '^4[^7FR^1] ^5TeamKit ^7- ^2Alien Arena' or v.get('Admin') != 'TeamKit' \
                or v.get('website') != 'https://teamkit.fr' or v.get('Admin/drapeau') != 's' or v.get('website/drapeau') != 's':
            soucis.append('défauts nom / Admin / website : %r %r %r' % (v.get('hostname'), v.get('Admin'), v.get('website')))
        for p in ('timelimit', 'fraglimit', 'warmuptime', 'g_spawnprotect', 'camptime', 'sv_botkickthreshold', 'skill',
                  'maxspectators', 'sv_public', 'allow_download', 'g_callvote', 'g_mapvote', 'g_autobalance'):
            if v.get(p) != defauts[p]:
                soucis.append('défaut %s : %r au lieu de %r' % (p, v.get(p), defauts[p]))
        if v.get('maxclients') != '16' or v.get('password') != '' or v.get('rcon_password') != '':
            soucis.append('défauts joueurs / mots de passe inattendus')
        if v.get('dmflags') != '2359312':
            soucis.append('dmflags par défaut %r : 2359312 attendu (valeur du server.cfg officiel)' % v.get('dmflags'))
        for p in ('ctf', 'g_tactical', 'g_duel', 'instagib', 'rocket_arena', 'insta_rockets', 'excessive', 'classbased',
                  'all_out_assault') + tuple(MUTATEURS):
            if v.get(p) != '0':
                soucis.append('défaut %s : %r au lieu de 0' % (p, v.get(p)))
        if v.get('sv_maplist') != 'dm-deathray dm-turbo dm-babel' or v.get('map') != ['dm-deathray']:
            soucis.append('rotation par défaut (ordre de maps.lst, cartes dm- présentes) : %r, carte %r'
                          % (v.get('sv_maplist'), v.get('map')))
        if v.get('setmaster') != ['master.alienarena.org', 'master2.alienarena.org']:
            soucis.append('liste publique : setmaster master.alienarena.org master2.alienarena.org attendu')
        if v.get('exec') != ['perso.cfg'] or v['__cmds__'][-1] != ['map', 'dm-deathray'] or '__macro__' in v:
            soucis.append('amp-teamkit.cfg doit finir par exec perso.cfg puis map, sans $')
        if r.get('amp-motd.txt') != 'Bienvenue sur le serveur francophone\nTeamKit !\nHeberge gratuitement par teamkit.fr\n' \
                                    'Discord : discord.gg/EuAjGMYPHY\n':
            soucis.append('message d’accueil par défaut : %r' % r.get('amp-motd.txt'))
        if 'perso.cfg' not in r or 'shadowtest' not in r.get('cartes', ''):
            soucis.append('perso.cfg ou cartes-disponibles.txt pas créés')
        if 'remplaces' in r['texte']:
            soucis.append('les textes par défaut ne devraient pas déclencher le remplacement des accents')
    # textes piégés : chaque valeur doit arriver entière, ASCII, sans " ; \
    PIEGES = {
        'Serveur francophone hébergé — TeamKit.fr · été « Œuvre »':
            "Serveur francophone heberge - TeamKit.fr - ete 'OEuvre'",
        'Dites "bonjour" ; 100 % fair-play // $hostname \\o/':
            "Dites 'bonjour' , 100 % fair-play // $hostname /o/",
        '^1Ça ^2c\'est l\'été': "^1Ca ^2c'est l'ete",
        '   espaces   autour   ': 'espaces autour',
        '': '',
    }
    for brut, attendu in PIEGES.items():
        for p in ('hostname', 'admin', 'website'):
            r = preparer({p: brut})
            n += 1
            cle = {'admin': 'Admin'}.get(p, p)
            lu = r.get('cfg', {}).get(cle)
            voulu = 'TeamKit - Alien Arena' if (p == 'hostname' and attendu == '') else attendu
            if r['code'] != 0 or lu != voulu:
                soucis.append('aller-retour %s %r : relu %r au lieu de %r\n%s' % (p, brut, lu, voulu, r['texte']))
            elif any(ch in (lu or '') for ch in '";\\') or any(ord(ch) > 127 for ch in lu or ''):
                soucis.append('aller-retour %s : caractère interdit dans %r' % (p, lu))
            elif '__macro__' in r['cfg']:
                soucis.append('aller-retour %s : un $ hors guillemets serait remplacé par le moteur' % p)
    r = preparer({'hostname': 'x' * 70})
    n += 1
    if r['code'] != 0 or r['cfg'].get('hostname') != 'x' * 63:
        soucis.append('nom de 70 caractères : coupé à 63 attendu (MAX_INFO_VALUE)')
    r = preparer({'motd': 'Ligne é « un » | | deux ; "trois" ' + 'mot ' * 20})
    n += 1
    if r['code'] != 0 or r.get('amp-motd.txt', '').split('\n')[:2] != ["Ligne e 'un'", "deux , 'trois' mot mot mot mot mot mot"] \
            or any(len(l) > 40 for l in r.get('amp-motd.txt', '').split('\n')):
        soucis.append('message d’accueil coupé / remplacé : %r' % r.get('amp-motd.txt'))
    r = preparer({'motd': ''})
    n += 1
    if r['code'] != 0 or r.get('amp-motd.txt') != '':
        soucis.append('message d’accueil vide : fichier vide attendu (pas de repli sur motd.txt du jeu)')
    # mots de passe : acceptés tels quels, ou refus net (code 1, message, pas de cfg)
    for mdp, accepte in [('Secret_rcon-42', True), ('a!b#c$d%e&f(g)h*i+j,k.l/m:n<o=p>q?r@s[t]u^v_w`x{y|z}~', True),
                         ('mon secret', False), ('été', False), ('a"b', False), ('a;b', False), ('a\\b', False),
                         ('x' * 64, False)]:
        for p in ('password', 'rcon_password'):
            r = preparer({p: mdp})
            n += 1
            if accepte and (r['code'] != 0 or r['cfg'].get(p) != mdp or '__macro__' in r['cfg']):
                soucis.append('mot de passe %r refusé ou abîmé pour %s' % (mdp, p))
            if not accepte and (r['code'] != 1 or 'ERREUR' not in r['texte'] or 'cfg' in r):
                soucis.append('mot de passe %r pour %s : il fallait un refus net' % (mdp, p))
            if mdp in r['texte'] and len(mdp) > 3:
                soucis.append('le mot de passe %r apparaît dans la console' % mdp)
    r = preparer({'password': 'none'})
    n += 1
    if r['code'] != 1 or 'none' not in r['texte']:
        soucis.append('mot de passe "none" : le jeu le lit comme « pas de mot de passe », refus attendu')
    r = preparer({'rcon_password': 'none'})
    n += 1
    if r['code'] != 0:
        soucis.append('mot de passe RCON "none" refusé à tort')
    # nombres et choix invalides : refus net
    for p, v in [('timelimit', 'abc'), ('timelimit', '1000'), ('fraglimit', '-1'), ('mode', 'ffa'), ('sv_public', '2'),
                 ('armes', 'tout'), ('skill', '4'), ('bots', 'oui'), ('vampire', '2'), ('sv_botkickthreshold', '33')]:
        r = preparer({p: v})
        n += 1
        if r['code'] != 1 or 'ERREUR' not in r['texte']:
            soucis.append('%s = %r : il fallait un refus net' % (p, v))
    for j, attendu in (('1', None), ('33', None), ('2', '2'), ('32', '32'), ('', '16')):
        r = preparer({}, joueurs=j)
        n += 1
        if attendu is None and r['code'] != 1:
            soucis.append('joueurs maximum %r : refus attendu' % j)
        if attendu is not None and (r['code'] != 0 or r['cfg'].get('maxclients') != attendu):
            soucis.append('joueurs maximum %r : %r au lieu de %r' % (j, r.get('cfg', {}).get('maxclients'), attendu))
    for p, v, cle, attendu in [('timelimit', '', 'timelimit', '20'), ('allow_download', 'False', 'allow_download', '0'),
                               ('allow_download', 'True', 'allow_download', '1'), ('sv_public', '0', 'sv_public', '0')]:
        r = preparer({p: v})
        n += 1
        if r['code'] != 0 or r['cfg'].get(cle) != attendu:
            soucis.append('%s = %r : relu %r au lieu de %r' % (p, v, r.get('cfg', {}).get(cle), attendu))
    r = preparer({'sv_public': '0'})
    if 'setmaster' in r['cfg']:
        soucis.append('serveur privé : pas de setmaster')
    # modes : cvars et dmflags (q_shared.h)
    for mode, ctf, tac, duel, maps, debut in [('ctf', '1', '0', '0', 'ctf-frost ctf-zion', 'ctf-frost'),
                                              ('tac', '0', '1', '0', 'tac-impact', 'tac-impact'),
                                              ('duel', '0', '0', '1', 'dm-deathray dm-turbo dm-babel', 'dm-deathray'),
                                              ('tdm', '0', '0', '0', 'dm-deathray dm-turbo dm-babel', 'dm-deathray')]:
        r = preparer({'mode': mode})
        n += 1
        v = r.get('cfg', {})
        if r['code'] != 0 or (v.get('ctf'), v.get('g_tactical'), v.get('g_duel')) != (ctf, tac, duel) \
                or v.get('sv_maplist') != maps or v.get('map') != [debut]:
            soucis.append('mode %s : ctf %r tactical %r duel %r rotation %r carte %r' % (
                mode, v.get('ctf'), v.get('g_tactical'), v.get('g_duel'), v.get('sv_maplist'), v.get('map')))
        if int(v.get('dmflags', 0)) & 64 != (64 if mode == 'tdm' else 0):
            soucis.append('mode %s : drapeau DF_SKINTEAMS (64) %s attendu' % (mode, 'mis' if mode == 'tdm' else 'absent'))
    for p, val, bit, mis in [('tir_allie', '0', 256, True), ('armes_restent', '1', 4, True), ('munitions_infinies', '1', 8192, True),
                             ('degats_chute', '0', 8, True), ('reapparition_forcee', '1', 1024, True), ('bots', '0', 1048576, True),
                             ('bots_parlent', '1', 262144, False)]:
        r = preparer({p: val})
        n += 1
        if r['code'] != 0 or bool(int(r['cfg']['dmflags']) & bit) != mis:
            soucis.append('%s = %s : bit %d de dmflags %s attendu' % (p, val, bit, 'mis' if mis else 'retiré'))
    r = preparer({'armes': 'insta_rockets', 'vampire': '1', 'grapple': 'True'})
    n += 1
    v = r.get('cfg', {})
    if r['code'] != 0 or v.get('insta_rockets') != '1' or v.get('instagib') != '0' or v.get('vampire') != '1' \
            or v.get('grapple') != '1' or v.get('low_grav') != '0':
        soucis.append('variante d’armes et mutateurs mal écrits')
    # cartes
    r = preparer({'sv_maplist': 'DM-Turbo, dm-inexistante;dm-babel dm-turbo ../x ctf-frost', 'map': 'dm-nulle'})
    n += 1
    if r['code'] != 0 or r['cfg'].get('sv_maplist') != 'dm-turbo dm-babel ctf-frost' or r['cfg'].get('map') != ['dm-turbo'] \
            or 'dm-inexistante' not in r['texte'] or 'dm-nulle' not in r['texte'] or 'ctf-frost' not in r['texte'] \
            or '../x' not in r['texte']:
        soucis.append('cartes inconnues : rotation %r, carte %r\n%s' % (r.get('cfg', {}).get('sv_maplist'),
                                                                       r.get('cfg', {}).get('map'), r['texte']))
    r = preparer({'sv_maplist': 'dm-inexistante', 'map': 'CTF-Zion'})
    n += 1
    if r['code'] != 0 or r['cfg'].get('sv_maplist') != 'dm-deathray dm-turbo dm-babel' or r['cfg'].get('map') != ['ctf-zion']:
        soucis.append('rotation sans carte valable : repli sur les cartes du mode attendu')

    def carte_ajoutee(tmp):
        os.makedirs(os.path.join(tmp, 'donnees', 'cor-games', 'arena', 'maps'))
        open(os.path.join(tmp, 'donnees', 'cor-games', 'arena', 'maps', 'dm-zzz-ajout.bsp'), 'wb').write(b'IBSP')
    r = preparer({}, avant=carte_ajoutee)
    n += 1
    if r['code'] != 0 or r['cfg'].get('sv_maplist') != 'dm-deathray dm-turbo dm-babel dm-zzz-ajout':
        soucis.append('carte ajoutée dans donnees/cor-games/arena/maps : absente de la rotation automatique')

    def sans_cartes_tac(tmp):
        os.remove(os.path.join(tmp, 'jeu', 'data1', 'maps', 'tac-impact.bsp'))
    r = preparer({'mode': 'tac'}, avant=sans_cartes_tac)
    n += 1
    if r['code'] != 1 or 'ERREUR' not in r['texte']:
        soucis.append('mode tactique sans carte tac- : refus net attendu')

    def perso_existant(tmp):
        open(os.path.join(tmp, 'donnees', 'cor-games', 'arena', 'perso.cfg'), 'w', newline='\n').write('set g_randomquad "1"\n')
    r = preparer({}, avant=perso_existant)
    n += 1
    if r.get('perso.cfg') != 'set g_randomquad "1"\n':
        soucis.append('perso.cfg du joueur réécrit')
    ok('aller-retour', '%d rendus AMP -> lanceur -> lecture façon moteur' % n)

# ── 8. le pont sur de vraies lignes (Alien Arena 7.72.3, 11 oct. 2026) ──────
# Sortie du serveur relevée dans les conteneurs jetables, avec deux vrais clients
# (^1Ke^4vin et Marine) et les bots de dm-deathray. Les réponses à la commande status
# cachée sont rejouées avec les tableaux réellement affichés par le serveur.
VRAIES = r'''------- Server Initialization -------
Loaded 276 entities
-------------------------------------
^1Ke^4vin connected
Call voting is ^2ENABLED
Antilagged projectiles are ^2ENABLED
^1Ke^4vin entered the game
^3Marty (bot) connected
Beavis (bot) connected
^9Si^4Borg (bot) connected
Beavis entered the game
^3Marty entered the game
^9Si^4Borg entered the game
#STATUT 1
Beavis: No...NO...NO ^9Si^4Borg!!
^9Si^4Borg: ^1Ke^4vin = pwned!
Marine connected
#STATUT 1
Marine entered the game
#STATUT 2
Marine: Bonjour : premier message
Marine: message equipe
#ATTENDRE 31
#STATUT 3
MarineBis: renommee
^1Ke^4vin: salut
Rcon from 172.17.0.32:45263:
rcon Essai-rcon42 "status" 
Bad rcon from 172.17.0.32:45263:
rcon mauvais "serverinfo" 
------- Server Initialization -------
Loaded 168 entities
-------------------------------------
#ATTENDRE 31
#STATUT 4
^1Ke^4vin was kicked
^1Ke^4vin disconnected
#STATUT 5
MarineBis disconnected
#STATUT 6
==== ShutdownGame ===='''
STATUTS = {
    '1': '''map              : dm-deathray
num score ping name            lastmsg address               qport
--- ----- ---- --------------- ------- --------------------- ------
  0     0 CNCT Kevin            103060 127.0.0.1:59767         985
  1     0   50 ^1Ke^4vin              2373 127.0.0.1:59069         314
''',
    '2': '''map              : dm-deathray
num score ping name            lastmsg address               qport
--- ----- ---- --------------- ------- --------------------- ------
  1     0   50 ^1Ke^4vin                50 127.0.0.1:59069         314
  2     0   46 Marine              859 127.0.0.1:34855         353
''',
    '3': '''map              : dm-deathray
num score ping name            lastmsg address               qport
--- ----- ---- --------------- ------- --------------------- ------
  1     0   52 ^1Ke^4vin              1568 127.0.0.1:59069         314
  2     0   46 MarineBis           859 127.0.0.1:34855         353
''',
    '4': '''map              : dm-babel
num score ping name            lastmsg address               qport
--- ----- ---- --------------- ------- --------------------- ------
  1     0 CNCT ^1Ke^4vin               120 127.0.0.1:59069         314
  2     0   46 MarineBis           859 127.0.0.1:34855         353
''',
    '5': '''map              : dm-babel
num score ping name            lastmsg address               qport
--- ----- ---- --------------- ------- --------------------- ------
  2     0   46 MarineBis           859 127.0.0.1:34855         353
''',
    '6': '''map              : dm-babel
num score ping name            lastmsg address               qport
--- ----- ---- --------------- ------- --------------------- ------
  2     0 ZMBI                     773 127.0.0.1:34855         353
''',
}
ATTENDU_PONT = [
    'TeamKit : serveur Alien Arena pret (port 27910 en UDP).',
    'TeamKit : Kevin a rejoint la partie (emplacement 1).',
    'TeamKit : Marine a rejoint la partie (emplacement 2).',
    '[Chat] Marine : Bonjour : premier message',
    '[Chat] Marine : message equipe',
    'TeamKit : Marine a quitte la partie (emplacement 2).',
    'TeamKit : MarineBis a rejoint la partie (emplacement 2).',
    '[Chat] MarineBis : renommee',
    '[Chat] Kevin : salut',
    'rcon *** "status" ',
    'rcon *** "serverinfo" ',
    'TeamKit : Kevin a quitte la partie (emplacement 1).',
    'TeamKit : MarineBis a quitte la partie (emplacement 2).',
]
sortie_pont = []
if PONT:
    espace = {'__name__': 'verifier'}
    try:
        exec(compile(PONT, 'pont', 'exec'), espace)
    except Exception as e:
        soucis.append('le pont ne se charge pas : %s' % e)
    if 'Pont' in espace:
        envoye = []
        pont = espace['Pont']('27910', envoye.append, sortie_pont.append, 'marque-essai')
        horloge = [1000.0]

        def repondre():
            """Le faux serveur : répond à la commande status cachée si le pont l'a envoyée."""
            while envoye:
                cmd = envoye.pop(0)
                if cmd == b'echo marque-essai-debut;status;echo marque-essai-fin\n':
                    yield cmd
                else:
                    soucis.append('pont : commande inattendue envoyée au serveur %r' % cmd)

        demandes = 0
        for ligne in VRAIES.split('\n'):
            if ligne.startswith('#ATTENDRE '):
                horloge[0] += float(ligne.split()[1])
                continue
            if ligne.startswith('#STATUT '):
                horloge[0] += 1
                pont.tic(horloge[0])
                faites = list(repondre())
                demandes += len(faites)
                if not faites:
                    soucis.append('pont : aucune commande status envoyée avant %s' % ligne)
                    continue
                for l in ['marque-essai-debut '] + STATUTS[ligne.split()[1]].rstrip('\n').split('\n') + ['', 'marque-essai-fin ']:
                    pont.ligne_du_jeu(l, horloge[0])
                continue
            horloge[0] += 0.1
            pont.ligne_du_jeu(ligne, horloge[0])
        horloge[0] += 31
        pont.tic(horloge[0])                    # plus personne : pas de status périodique
        if envoye:
            soucis.append('pont : status demandé alors que le serveur est vide')
        pont.commande_amp(b'say Bonjour depuis AMP\r\nsta', horloge[0])
        pont.commande_amp(b'tus\n' + b'x' * 300 + b'\nquit\n', horloge[0])
        if envoye != [b'say Bonjour depuis AMP\n', b'status\n', b'x' * 250 + b'\n', b'quit\n'] or not pont.arret:
            soucis.append('pont : commandes d’AMP mal transmises %r' % envoye[:3])
        ajoutees = [l for l in sortie_pont if l.startswith(('TeamKit : ', '[Chat', 'rcon '))]
        if ajoutees != ATTENDU_PONT:
            soucis.append('pont :\n       obtenu  %s\n       attendu %s' % (ajoutees, ATTENDU_PONT))
        elif any('marque-essai' in l or l.startswith(('num score', '--- -----', 'map              :'))
                 or '127.0.0.1:' in l for l in sortie_pont):
            soucis.append('pont : la réponse de la commande status cachée apparaît dans la console')
        elif any('Essai-rcon42' in l for l in sortie_pont):
            soucis.append('pont : mot de passe RCON visible dans la console')
        else:
            ok('pont', '%d lignes réelles, %d commandes status cachées, %d lignes produites (arrivées, bots '
               'ignorés, chat, renommage, RCON masqué, exclusion, départ)' % (len(VRAIES.split('\n')), demandes,
                                                                            len(ajoutees)))
        # réponse incomplète : les lignes cachées sont rendues au bout de 5 s
        p2, sortie2 = espace['Pont']('27910', [].append, [].append, 'm'), []
        p2.sortir = sortie2.append
        p2.ligne_du_jeu('m-debut', 10.0)
        p2.ligne_du_jeu('ligne coincee', 10.0)
        p2.tic(16.0)
        if sortie2 != ['ligne coincee']:
            soucis.append('pont : lignes cachées perdues si la réponse status ne finit pas')
        nj = espace['nom_jeu']
        if nj('Un\tnom tres tres long qui depasse') != 'Un nom tres tre' or nj('^1A^2B') != '^1A^2B':
            soucis.append('pont : nom_jeu ne suit pas ValidatePlayerName')

# ── 9. regex de console ──────────────────────────────────────────────────────
filtre_amp = py(cles['Console.FilterMatchRegex'])
ESSAIS = [
    ('Console.AppReadyRegex', 'TeamKit : serveur Alien Arena pret (port 27910 en UDP).', {}),
    ('Console.UserJoinRegex', 'TeamKit : Kevin a rejoint la partie (emplacement 0).', {'username': 'Kevin', 'userid': '0'}),
    ('Console.UserJoinRegex', 'TeamKit : [FR]Jean-Luc (2) a rejoint la partie (emplacement 15).',
     {'username': '[FR]Jean-Luc (2)', 'userid': '15'}),
    ('Console.UserLeaveRegex', 'TeamKit : MarineBis a quitte la partie (emplacement 2).', {'username': 'MarineBis', 'userid': '2'}),
    ('Console.UserChatRegex', '[Chat] Marine : Bonjour : premier message', {'username': 'Marine', 'message': 'Bonjour : premier message'}),
    ('Console.UserChatRegex', '[Chat equipe] Kevin : on attaque', {'username': 'Kevin', 'message': 'on attaque'}),
    ('Console.ThrowawayMessageRegex', 'Unknown command "unbindall"', {}),
    ('Console.ThrowawayMessageRegex', 'Could not exec config.cfg', {}),
    ('Console.ThrowawayMessageRegex', 'Searching for collision file at /AMP/alienarena/jeu/data1/maps/meshes/dm-babel/lavarock1.terrainx', {}),
]
for cle, ligne, attendu in ESSAIS:
    for version in (ligne, filtre_amp.sub(cles['Console.FilterMatchReplacement'], ligne)):
        mm = py(cles.get(cle) or '^$').search(version)
        if not mm or any(mm.group(k) != v for k, v in attendu.items()):
            soucis.append('%s ne reconnaît pas : %r' % (cle, version))
PIEGES = [
    ('Console.UserJoinRegex', '^1Ke^4vin entered the game'),
    ('Console.UserJoinRegex', 'TeamKit : Kevin a quitte la partie (emplacement 0).'),
    ('Console.UserJoinRegex', '[Chat] Kevin : TeamKit : Bob a rejoint la partie (emplacement 3).'),
    ('Console.UserLeaveRegex', 'TeamKit : Kevin a rejoint la partie (emplacement 0).'),
    ('Console.UserLeaveRegex', 'MarineBis disconnected'),
    ('Console.UserChatRegex', 'Beavis: No...NO...NO ^9Si^4Borg!!'),
    ('Console.UserChatRegex', 'Game sub-directory: /AMP/alienarena/jeu/arena'),
    ('Console.AppReadyRegex', '-------------------------------------'),
    ('Console.AppReadyRegex', '[Chat] Kevin : TeamKit : serveur Alien Arena pret (port 27910 en UDP).'),
    ('Console.ThrowawayMessageRegex', 'Marine entered the game'),
    ('Console.ThrowawayMessageRegex', 'Unknown command "statuss"'),
]
for cle, ligne in PIEGES:
    if py(cles[cle]).search(ligne):
        soucis.append('%s attrape une ligne qui n’est pas pour lui : %r' % (cle, ligne))
if filtre_amp.sub('', '^9Si^4Borg: ^1Ke^4vin = pwned!') != 'SiBorg: Kevin = pwned!':
    soucis.append('FilterMatchRegex doit retirer les codes couleur ^0 à ^9')
for l in sortie_pont:
    if l.startswith('TeamKit : ') and 'pret' not in l and not (py(cles['Console.UserJoinRegex']).search(l)
                                                            or py(cles['Console.UserLeaveRegex']).search(l)):
        soucis.append('ligne du pont reconnue par aucune regex : %r' % l)
    if l.startswith('[Chat') and not py(cles['Console.UserChatRegex']).search(l):
        soucis.append('ligne de chat du pont non reconnue : %r' % l)
ok('console', '%d lignes (avec et sans FilterMatchRegex), %d pièges' % (len(ESSAIS), len(PIEGES)))

print()
if soucis:
    print('%d problème(s) :' % len(soucis))
    print('\n'.join('  NON  ' + s for s in soucis))
    sys.exit(1)
print('Tout est bon.')
