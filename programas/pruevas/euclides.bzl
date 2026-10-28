Main |:
    <w> "Escribe dos numeros"
    <?> a
    <?> b
    Euclides a b
:|

Euclides a b |:
    if b = 0 |:
        <w> "Su MCD es" a
    :| else |:
        Euclides b (a % b)
    :|
:|