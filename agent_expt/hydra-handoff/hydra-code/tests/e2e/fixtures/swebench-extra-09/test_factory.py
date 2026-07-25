from factory import get_connection, reset_connection


def test_same_config_same_instance():
    reset_connection()
    c1 = get_connection("db1", 5432)
    c2 = get_connection("db1", 5432)
    assert c1 is c2


def test_different_config_different_instance():
    reset_connection()
    c1 = get_connection("db1", 5432)
    c2 = get_connection("db2", 5432)
    assert c1 is not c2, "Different configs should return different instances!"


def test_host_port_preserved():
    reset_connection()
    c = get_connection("myhost", 9999)
    assert c.host == "myhost"
    assert c.port == 9999
