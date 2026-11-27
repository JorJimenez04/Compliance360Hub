"""Restablecer la clave de un cliente: solo el super_admin, solo clientes, clave visible una vez.

Las pruebas con base usan PostgreSQL real (TX_TEST_PG_URL); el resto corre sin base.
"""

from __future__ import annotations

import os
import pathlib

import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

pytest.importorskip("sqlalchemy")

from api import seguridad as seg  # noqa: E402
from api.claves import clave_temporal, hash_clave  # noqa: E402
from api.rutas import usuarios as ru  # noqa: E402


def _dependencia(ruta: str, metodo: str):
    for r in ru.router.routes:
        if isinstance(r, APIRoute) and r.path == ruta and metodo in r.methods:
            return next(d.call for d in r.dependant.dependencies if d.call.__name__ == "_dep")
    raise AssertionError(f"Falta la ruta {metodo} {ruta}")


RUTAS = [("/api/usuarios/clientes", "GET"), ("/api/usuarios/clientes/{usuario_id}/restablecer-clave", "POST"),
         ("/api/usuarios", "GET"), ("/api/usuarios", "POST"), ("/api/usuarios/{usuario_id}", "PATCH"),
         ("/api/usuarios/{usuario_id}/restablecer-clave", "POST")]


def test_no_hay_rutas_de_usuarios_sin_clasificar():
    """Toda ruta de administración de usuarios debe estar en RUTAS (y por tanto exigir super_admin)."""
    reales = {(r.path, m) for r in ru.router.routes if isinstance(r, APIRoute) for m in r.methods}
    assert reales == set(RUTAS)


@pytest.mark.parametrize("rol", ["admin", "compliance", "cliente", "junta", "agente", "manager_ops", "cic"])
@pytest.mark.parametrize("ruta, metodo", RUTAS)
def test_solo_el_super_admin_entra(rol, ruta, metodo):
    dep = _dependencia(ruta, metodo)
    with pytest.raises(HTTPException) as e:
        dep(seg.Usuario(5, "x", "X", rol))
    assert e.value.status_code == 403


@pytest.mark.parametrize("ruta, metodo", RUTAS)
def test_el_super_admin_pasa(ruta, metodo):
    u = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    assert _dependencia(ruta, metodo)(u) is u


def test_el_menu_de_usuarios_solo_lo_ve_el_super_admin():
    assert "usuarios" in seg.modulos_visibles("super_admin")
    for rol in ("admin", "compliance", "cliente", "junta"):
        assert "usuarios" not in seg.modulos_visibles(rol)
    # Organizaciones: todo el equipo interno la consulta (crear y editar sigue siendo solo del super_admin)
    for rol in ("admin", "compliance", "director_cumplimiento"):
        assert "organizaciones" in seg.modulos_visibles(rol)
    for rol in ("cliente", "junta"):
        assert "organizaciones" not in seg.modulos_visibles(rol)


def test_clave_temporal_es_fuerte_y_el_hash_la_verifica():
    claves = {clave_temporal() for _ in range(50)}
    assert len(claves) == 50
    for c in claves:
        assert len(c) == 16 and any(x.islower() for x in c) and any(x.isupper() for x in c) and any(x.isdigit() for x in c)
    assert bcrypt.checkpw(b"abc", hash_clave("abc").encode())


# ---------- Contra PostgreSQL ----------
@pytest.fixture
def pg(monkeypatch):
    url = os.getenv("TX_TEST_PG_URL")
    if not url:
        pytest.skip("Defina TX_TEST_PG_URL para probar contra PostgreSQL")
    from sqlalchemy import create_engine, text
    import db.database as bd
    from tests._esquema import crear_esquema_minimo
    engine = create_engine(url)
    crear_esquema_minimo(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO tx_empresas (nombre_reporte) VALUES ('Mi Empresa')"))
        conn.execute(text("INSERT INTO usuarios (username, nombre_completo, rol, password_hash, activo, "
                          "organizacion_id, alcance) SELECT 'cli', 'Cliente Uno', 'cliente', 'viejo', 0, id, 'empresas' "
                          "FROM organizaciones WHERE nombre = 'Adamo'"))
        conn.execute(text("INSERT INTO usuarios (username, nombre_completo, rol, password_hash, activo) VALUES "
                          "('interno', 'Interno', 'compliance', 'intacto', 1), "
                          "('jefazo', 'Otro super', 'super_admin', 'intacto', 1)"))
        conn.execute(text("INSERT INTO usuario_empresas SELECT u.id, e.id, now() FROM usuarios u, tx_empresas e "
                          "WHERE u.username = 'cli'"))
    monkeypatch.setattr(bd, "engine", engine)
    registros = []
    monkeypatch.setattr(seg, "auditar", lambda *a, **k: registros.append((a, k)))
    yield engine, registros
    engine.dispose()


class _Peticion:
    headers: dict = {}
    client = None


def _id(engine, username):
    from sqlalchemy import text
    with engine.connect() as c:
        return c.execute(text("SELECT id FROM usuarios WHERE username = :u"), {"u": username}).scalar_one()


def test_listar_clientes_trae_solo_clientes_con_sus_empresas(pg):
    engine, _ = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    lista = ru.listar_clientes(jefe)["clientes"]
    assert [c["username"] for c in lista] == ["cli"]
    assert lista[0]["empresas"] == "Mi Empresa" and lista[0]["activo"] is False


def test_restablecer_cambia_la_clave_reactiva_y_audita(pg):
    from sqlalchemy import text
    engine, registros = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    r = ru.restablecer_clave(_id(engine, "cli"), _Peticion(), jefe)
    assert r["username"] == "cli" and len(r["clave_temporal"]) == 16
    with engine.connect() as c:
        h, activo = c.execute(text("SELECT password_hash, activo FROM usuarios WHERE username = 'cli'")).one()
    assert bcrypt.checkpw(r["clave_temporal"].encode(), h.encode())   # en la base solo queda el hash
    assert r["clave_temporal"] not in h and activo == 1
    assert len(registros) == 1 and registros[0][0][1] == "UPDATE"
    assert r["clave_temporal"] not in str(registros)                    # la clave no llega a la auditoría


def test_no_se_puede_tocar_a_un_usuario_interno_ni_inexistente(pg):
    from sqlalchemy import text
    engine, registros = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    for uid in (_id(engine, "interno"), 999999):
        with pytest.raises(HTTPException) as e:
            ru.restablecer_clave(uid, _Peticion(), jefe)
        assert e.value.status_code == 404
    with engine.connect() as c:
        assert c.execute(text("SELECT password_hash FROM usuarios WHERE username = 'interno'")).scalar_one() == "intacto"
    assert registros == []


# ---------- Cuenta de emergencia (ADMIN_USERNAME) vs. usuario de la base ----------
def test_la_cuenta_de_emergencia_con_usuario_en_la_base_toma_su_rol(pg, monkeypatch):
    from sqlalchemy import text
    engine, _ = pg
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO usuarios (username, nombre_completo, rol, password_hash, activo) "
                          "VALUES ('jefe', 'Jefe Real', 'super_admin', 'x', 1)"))
    monkeypatch.setenv("ADMIN_USERNAME", "jefe")
    monkeypatch.setenv("ADMIN_PASSWORD", "Clave_De_Prueba_2026!")
    u = seg.autenticar("jefe", "Clave_De_Prueba_2026!")
    assert u.rol == "super_admin" and u.id == _id(engine, "jefe") and u.nombre == "Jefe Real"
    assert "usuarios" in seg.modulos_visibles(u.rol)


def test_la_cuenta_de_emergencia_sin_usuario_en_la_base_sigue_siendo_admin(pg, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "emergencia")
    monkeypatch.setenv("ADMIN_PASSWORD", "Clave_De_Prueba_2026!")
    u = seg.autenticar("emergencia", "Clave_De_Prueba_2026!")
    assert u.rol == "admin" and u.id == 0
    assert seg.autenticar("emergencia", "otra") is None


def test_la_cuenta_de_emergencia_no_hereda_el_rol_de_un_usuario_inactivo(pg, monkeypatch):
    from sqlalchemy import text
    engine, _ = pg
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO usuarios (username, rol, password_hash, activo) VALUES ('baja', 'super_admin', 'x', 0)"))
    monkeypatch.setenv("ADMIN_USERNAME", "baja")
    monkeypatch.setenv("ADMIN_PASSWORD", "Clave_De_Prueba_2026!")
    assert seg.autenticar("baja", "Clave_De_Prueba_2026!").rol == "admin"


# ---------- Alta y cambios de usuarios (multi-organización) ----------
def _crear(datos, jefe=None):
    return ru.crear(ru.NuevoUsuario(**datos), _Peticion(), jefe or seg.Usuario(1, "jefe", "Jefe", "super_admin"))


def _org(engine, nombre="Adamo"):
    from sqlalchemy import text
    with engine.begin() as c:
        fila = c.execute(text("SELECT id FROM organizaciones WHERE nombre = :n"), {"n": nombre}).scalar()
        return fila or c.execute(text("INSERT INTO organizaciones (nombre) VALUES (:n) RETURNING id"),
                                 {"n": nombre}).scalar_one()


def _empresa(engine, nombre, org):
    from sqlalchemy import text
    with engine.begin() as c:
        return c.execute(text("INSERT INTO tx_empresas (nombre_reporte, organizacion_id) VALUES (:n, :o) RETURNING id"),
                         {"n": nombre, "o": org}).scalar_one()


def test_crear_cliente_de_toda_la_organizacion_y_junta(pg):
    from sqlalchemy import text
    engine, registros = pg
    org = _org(engine)
    r = _crear({"username": "equipo.adamo", "nombre": "Equipo Adamo", "email": "Equipo@Adamo.co",
                "rol": "cliente", "organizacion_id": org, "alcance": "organizacion"})
    j = _crear({"username": "ceo.adamo", "nombre": "CEO", "email": "ceo@adamo.co", "rol": "junta", "organizacion_id": org})
    with engine.connect() as c:
        fila = c.execute(text("SELECT rol, organizacion_id, alcance, email, password_hash FROM usuarios WHERE id = :i"),
                         {"i": r["id"]}).one()
        junta = c.execute(text("SELECT rol, organizacion_id, alcance FROM usuarios WHERE id = :i"), {"i": j["id"]}).one()
    assert fila[:4] == ("cliente", org, "organizacion", "equipo@adamo.co")
    assert bcrypt.checkpw(r["clave_temporal"].encode(), fila[4].encode())
    assert junta == ("junta", org, None)
    assert r["clave_temporal"] not in str(registros)


@pytest.mark.parametrize("datos, codigo", [
    ({"rol": "junta"}, 400),                                                    # sin organización
    ({"rol": "cliente", "organizacion_id": "ORG"}, 400),                         # sin alcance
    ({"rol": "cliente", "organizacion_id": "ORG", "alcance": "empresas"}, 400),  # 'empresas' sin empresas
    ({"rol": "compliance", "organizacion_id": "ORG"}, 400),                      # interno con organización
    ({"rol": "super_admin"}, 400),                                               # perfil no gestionable
    ({"rol": "junta", "organizacion_id": "ORG", "alcance": "organizacion"}, 400),
    ({"rol": "cliente", "organizacion_id": 999999, "alcance": "organizacion"}, 404),
])
def test_reglas_de_alta(pg, datos, codigo):
    engine, _ = pg
    org = _org(engine)
    datos = {k: (org if v == "ORG" else v) for k, v in datos.items()}
    with pytest.raises(HTTPException) as e:
        _crear({"username": "nuevo", "nombre": "Nuevo", "email": "n@x.co", **datos})
    assert e.value.status_code == codigo


def test_no_se_asignan_empresas_de_otra_organizacion(pg):
    engine, _ = pg
    adamo, otra = _org(engine), _org(engine, "CM Grupo Tecno")
    ajena = _empresa(engine, "Empresa de CM", otra)
    with pytest.raises(HTTPException) as e:
        _crear({"username": "cli.x", "nombre": "Equis", "email": "x@x.co", "rol": "cliente",
                "organizacion_id": adamo, "alcance": "empresas", "empresas": [ajena]})
    assert e.value.status_code == 400


def test_no_se_crea_en_una_organizacion_inactiva(pg):
    from sqlalchemy import text
    engine, _ = pg
    org = _org(engine, "Inactiva")
    with engine.begin() as c:
        c.execute(text("UPDATE organizaciones SET activa = FALSE WHERE id = :o"), {"o": org})
    with pytest.raises(HTTPException) as e:
        _crear({"username": "cli.y", "nombre": "Ye", "email": "y@x.co", "rol": "junta", "organizacion_id": org})
    assert e.value.status_code == 400


def test_usuario_o_correo_repetido_responde_409(pg):
    engine, _ = pg
    org = _org(engine)
    base = {"nombre": "Zeta", "rol": "junta", "organizacion_id": org}
    _crear({"username": "unico", "email": "unico@x.co", **base})
    for repetido in ({"username": "unico", "email": "otro@x.co"}, {"username": "otro", "email": "UNICO@x.co"}):
        with pytest.raises(HTTPException) as e:
            _crear({**repetido, **base})
        assert e.value.status_code == 409


def test_los_clientes_de_los_clientes_no_tienen_acceso(pg):
    """Decisión 2026-11-23: no se crea ni se reactiva un usuario de alcance 'empresas'."""
    from sqlalchemy import text
    engine, _ = pg
    org = _org(engine)
    e1 = _empresa(engine, "E1", org)
    with pytest.raises(HTTPException) as e:
        _crear({"username": "cli.z", "nombre": "Zeta", "email": "z@x.co", "rol": "cliente",
                "organizacion_id": org, "alcance": "empresas", "empresas": [e1]})
    assert e.value.status_code == 400
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    viejo = _id(engine, "cli")                               # cliente de la 037, alcance 'empresas', inactivo
    with pytest.raises(HTTPException):
        ru.cambiar(viejo, ru.CambioUsuario(activo=True), _Peticion(), jefe)
    # Convertirlo en usuario del equipo de la organización sí es posible
    ru.cambiar(viejo, ru.CambioUsuario(alcance="organizacion", activo=True), _Peticion(), jefe)
    with engine.connect() as c:
        assert c.execute(text("SELECT alcance, activo FROM usuarios WHERE id = :u"), {"u": viejo}).one() == ("organizacion", 1)
        assert c.scalar(text("SELECT count(*) FROM usuario_empresas WHERE usuario_id = :u"), {"u": viejo}) == 0
    r = _crear({"username": "equipo.z", "nombre": "Zeta", "email": "z2@x.co", "rol": "cliente",
                "organizacion_id": org, "alcance": "organizacion"})
    ru.cambiar(r["id"], ru.CambioUsuario(activo=False), _Peticion(), jefe)
    with engine.connect() as c:
        assert c.scalar(text("SELECT activo FROM usuarios WHERE id = :u"), {"u": r["id"]}) == 0


def test_no_se_gestiona_a_otro_super_admin(pg):
    engine, _ = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    for llamada in (lambda: ru.restablecer(_id(engine, "jefazo"), _Peticion(), jefe),
                    lambda: ru.cambiar(_id(engine, "jefazo"), ru.CambioUsuario(activo=False), _Peticion(), jefe)):
        with pytest.raises(HTTPException) as e:
            llamada()
        assert e.value.status_code == 404


def test_listado_trae_organizacion_y_alcance(pg):
    engine, _ = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    lista = {x["username"]: x for x in ru.listar(jefe)["usuarios"]}
    assert set(lista) == {"cli", "interno"}                   # el otro super_admin no aparece
    assert lista["cli"]["organizacion"] == "Adamo" and lista["cli"]["alcance"] == "empresas"
    assert lista["interno"]["organizacion"] is None


def test_organizacion_desactivada_saca_a_sus_usuarios(pg, monkeypatch):
    """Login y sesión abierta: ninguno funciona si la organización del usuario está inactiva."""
    from sqlalchemy import text
    engine, _ = pg
    org = _org(engine, "Saliente")
    r = _crear({"username": "ceo.sal", "nombre": "CEO", "email": "ceo@sal.co", "rol": "junta", "organizacion_id": org})
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    u = seg.autenticar("ceo.sal", r["clave_temporal"])
    assert u is not None and u.organizacion_id == org and seg.sigue_activo(u)
    with engine.begin() as c:
        c.execute(text("UPDATE organizaciones SET activa = FALSE WHERE id = :o"), {"o": org})
    assert seg.sigue_activo(u) is False
    assert seg.autenticar("ceo.sal", r["clave_temporal"]) is None


def _con_clave(engine, username, clave, rol="director_cumplimiento"):
    from sqlalchemy import text
    from api.claves import hash_clave
    with engine.begin() as c:
        c.execute(text("INSERT INTO usuarios (username, nombre_completo, email, rol, password_hash, activo) "
                       "VALUES (:u, :u, :e, :r, :h, 1)"), {"u": username, "e": f"{username}@x.co", "r": rol, "h": hash_clave(clave)})


def test_el_usuario_no_distingue_mayusculas_y_la_clave_tolera_espacios(pg):
    engine, _ = pg
    _con_clave(engine, "Diego_Perez", "Ab3defGhjkMnpQr9")
    for escrito in ("Diego_Perez", "diego_perez", "DIEGO_PEREZ"):
        u = seg.autenticar(escrito, "Ab3defGhjkMnpQr9")
        assert u is not None and u.username == "Diego_Perez" and u.rol == "director_cumplimiento"
    assert seg.autenticar("diego_perez", "  Ab3defGhjkMnpQr9\n") is not None     # espacio colado al copiar
    assert seg.autenticar("diego_perez", "ab3defGhjkMnpQr9") is None             # la clave sí distingue mayúsculas
    assert seg.autenticar("diego_perez", "Ab3def Ghjk") is None


def test_usuarios_antiguos_que_solo_difieren_en_mayusculas_exigen_la_forma_exacta(pg):
    engine, _ = pg
    _con_clave(engine, "ana", "Clave1Uno2Dos3Tr", "compliance")
    _con_clave(engine, "Ana", "Clave1Uno2Dos3Tr", "compliance")
    assert seg.autenticar("ANA", "Clave1Uno2Dos3Tr") is None                     # ambiguo: no adivina
    assert seg.autenticar("Ana", "Clave1Uno2Dos3Tr").username == "Ana"
    assert seg.autenticar("ana", "Clave1Uno2Dos3Tr").username == "ana"


def test_los_usuarios_nuevos_se_guardan_en_minusculas_y_no_se_duplican(pg):
    from fastapi import HTTPException
    engine, _ = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    r = ru.crear(ru.NuevoUsuario(username="Maria.Lopez", nombre="María López", email="Maria@X.co",
                                 rol="director_cumplimiento"), _Peticion(), jefe)
    assert r["username"] == "maria.lopez"
    with pytest.raises(HTTPException) as e:
        ru.crear(ru.NuevoUsuario(username="MARIA.LOPEZ", nombre="Otra", email="otra@x.co", rol="compliance"), _Peticion(), jefe)
    assert e.value.status_code == 409
    assert seg.autenticar("Maria.Lopez", r["clave_temporal"]).username == "maria.lopez"


# ---------- Clave escrita a mano por el super_admin ----------
CLAVE_MANUAL = "Adamo2026Segura"


def test_crear_con_clave_escrita_no_la_devuelve_ni_la_audita(pg):
    engine, registros = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    r = ru.crear(ru.NuevoUsuario(username="laura", nombre="Laura", email="laura@x.co", rol="compliance",
                                 clave=CLAVE_MANUAL), _Peticion(), jefe)
    assert r["clave_temporal"] is None
    assert seg.autenticar("laura", CLAVE_MANUAL).username == "laura"
    assert CLAVE_MANUAL not in str(registros) and "asignada a mano" in str(registros)


@pytest.mark.parametrize("debil", ["Corta1A", "todominuscula123", "TODOMAYUSCULA123", "SinNumerosNiNada",
                                   " Adamo2026Segura", "Adamo2026Segura "])
def test_una_clave_debil_se_rechaza(pg, debil):
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    with pytest.raises(HTTPException) as e:
        ru.crear(ru.NuevoUsuario(username="pedro", nombre="Pedro", email="pedro@x.co", rol="compliance",
                                 clave=debil), _Peticion(), jefe)
    assert e.value.status_code == 400


def test_restablecer_con_clave_escrita(pg):
    engine, registros = pg
    jefe = seg.Usuario(1, "jefe", "Jefe", "super_admin")
    _con_clave(engine, "diego", "Vieja1ClaveLarga")
    r = ru.restablecer(_id(engine, "diego"), _Peticion(), jefe, ru.ClaveManual(clave=CLAVE_MANUAL))
    assert r["clave_temporal"] is None
    assert seg.autenticar("diego", CLAVE_MANUAL) is not None
    assert seg.autenticar("diego", "Vieja1ClaveLarga") is None
    assert CLAVE_MANUAL not in str(registros)
    # sin cuerpo sigue generando una al azar
    g = ru.restablecer(_id(engine, "diego"), _Peticion(), jefe)
    assert len(g["clave_temporal"]) == 16 and seg.autenticar("diego", g["clave_temporal"]) is not None


# ---------- Cuentas internas visibles, duplicados claros y edición completa ----------
JEFE = seg.Usuario(1, "jefe", "Jefe", "super_admin")


def test_el_listado_muestra_las_cuentas_internas_aparte(pg):
    r = ru.listar(JEFE)
    assert "jefazo" in [x["username"] for x in r["internos"]]
    assert "jefazo" not in [x["username"] for x in r["usuarios"]]
    assert "interno" in [x["username"] for x in r["usuarios"]]          # compliance sí se gestiona


def test_el_duplicado_dice_que_cuenta_lo_tiene(pg):
    from sqlalchemy import text
    engine, _ = pg
    with engine.begin() as c:
        c.execute(text("UPDATE usuarios SET email = 'jorge@adamo.co' WHERE username = 'jefazo'"))
    with pytest.raises(HTTPException) as e:
        _crear(dict(username="nuevo", nombre="Nuevo", email="Jorge@Adamo.co", rol="compliance"))
    assert e.value.status_code == 409 and "«jefazo» (Super admin)" in e.value.detail and "correo" in e.value.detail
    with pytest.raises(HTTPException) as e:
        _crear(dict(username="JEFAZO", nombre="Nuevo", email="otro@x.co", rol="compliance"))
    assert "El usuario «jefazo»" in e.value.detail


def test_editar_usuario_nombre_y_rol(pg):
    from sqlalchemy import text
    engine, _ = pg
    uid = _id(engine, "interno")
    ru.cambiar(uid, ru.CambioUsuario(username="Diego.P", rol="director_cumplimiento"), _Peticion(), JEFE)
    with engine.connect() as c:
        assert c.execute(text("SELECT username, rol FROM usuarios WHERE id = :i"), {"i": uid}).one() == \
            ("diego.p", "director_cumplimiento")
    with pytest.raises(HTTPException) as e:                              # usuario ocupado por otra cuenta
        ru.cambiar(uid, ru.CambioUsuario(username="jefazo"), _Peticion(), JEFE)
    assert e.value.status_code == 409
    ru.cambiar(uid, ru.CambioUsuario(username="DIEGO.P", nombre="Diego"), _Peticion(), JEFE)   # el propio no choca


def test_pasar_de_interno_a_cliente_y_mover_de_organizacion(pg):
    from sqlalchemy import text
    engine, _ = pg
    adamo, otra = _org(engine), _org(engine, "Paycop")
    uid = _id(engine, "interno")
    with pytest.raises(HTTPException):                                   # cliente sin organización
        ru.cambiar(uid, ru.CambioUsuario(rol="cliente"), _Peticion(), JEFE)
    ru.cambiar(uid, ru.CambioUsuario(rol="cliente", organizacion_id=adamo), _Peticion(), JEFE)
    ru.cambiar(uid, ru.CambioUsuario(organizacion_id=otra), _Peticion(), JEFE)
    with engine.connect() as c:
        assert c.execute(text("SELECT rol, organizacion_id, alcance FROM usuarios WHERE id = :i"), {"i": uid}).one() == \
            ("cliente", otra, "organizacion")
    ru.cambiar(uid, ru.CambioUsuario(rol="compliance"), _Peticion(), JEFE)       # vuelve al equipo interno
    with engine.connect() as c:
        assert c.execute(text("SELECT organizacion_id, alcance FROM usuarios WHERE id = :i"), {"i": uid}).one() == (None, None)
    with pytest.raises(HTTPException):
        ru.cambiar(uid, ru.CambioUsuario(rol="super_admin"), _Peticion(), JEFE)


def test_los_perfiles_de_la_app_anterior_se_ven_y_se_nombran(pg):
    from sqlalchemy import text
    engine, _ = pg
    with engine.begin() as c:
        c.execute(text("INSERT INTO usuarios (username, nombre_completo, email, rol, password_hash, activo) "
                       "VALUES ('viejo', 'Viejo', 'viejo@x.co', 'manager_ops', 'x', 1)"))
    internos = {x["username"]: x for x in ru.listar(JEFE)["internos"]}
    assert internos["viejo"]["perfil"] == "Gerente de operaciones (app anterior)"
    with pytest.raises(HTTPException) as e:
        _crear(dict(username="otro", nombre="Otro", email="VIEJO@x.co", rol="compliance"))
    assert "«viejo» (Gerente de operaciones (app anterior))" in e.value.detail
