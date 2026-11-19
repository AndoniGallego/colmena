import asyncio

import contrato
import pytest
from arneses import arnes_fake, arnes_herdr

CASOS = [n for n in dir(contrato) if n.startswith("caso_")]


@pytest.mark.parametrize("fabrica", [arnes_fake, arnes_herdr], ids=["fake", "herdr"])
@pytest.mark.parametrize("caso", CASOS)
def test_contrato(fabrica, caso):
    asyncio.run(getattr(contrato, caso)(fabrica()))
