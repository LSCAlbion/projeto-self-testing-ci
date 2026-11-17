import csv
import glob
import os
import subprocess
import sys
import time
import httpx


def wait_for_server(url: str, timeout: float = 10.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(f"{url}/docs", timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    print("==========================================================")
    print("Iniciando Teste de Carga Concorrente (Locust - 50 Usuários)")
    print("==========================================================")

    # 1. Inicia o servidor FastAPI em processo separado
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///./load_test.db"
    env["MOCK_EXTERNAL_SERVICES"] = "true"

    server_cmd = [
        sys.executable, "-m", "uvicorn",
        "src.controllers.api:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--log-level", "warning",
    ]
    print("-> Subindo servidor FastAPI em http://127.0.0.1:8000...")
    server_process = subprocess.Popen(server_cmd, env=env)

    try:
        if not wait_for_server("http://127.0.0.1:8000", timeout=12.0):
            print("ERRO: O servidor nao subiu a tempo.")
            return

        print("-> Servidor online! Executando teste de carga com Locust...")
        # 2. Executa Locust em modo headless com 50 usuários simultâneos
        locust_cmd = [
            sys.executable, "-m", "locust",
            "-f", "locustfile.py",
            "--host", "http://127.0.0.1:8000",
            "--headless",
            "-u", "50",
            "-r", "10",
            "--run-time", "12s",
            "--csv", "load_report",
        ]
        subprocess.run(locust_cmd, check=True)

        print("\n-> Teste concluido! Analisando relatorio gerado...")
        # 3. Lê o arquivo de resumo de estatísticas
        stats_file = "load_report_stats.csv"
        if os.path.exists(stats_file):
            with open(stats_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Name") == "Aggregated":
                        req_count = row.get("Request Count", "0")
                        fail_count = row.get("Failure Count", "0")
                        avg_latency = row.get("Average Response Time", "0")
                        min_latency = row.get("Min Response Time", "0")
                        max_latency = row.get("Max Response Time", "0")
                        rps = row.get("Requests/s", "0")

                        fail_rate = (float(fail_count) / float(req_count) * 100) if float(req_count) > 0 else 0.0

                        print("----------------------------------------------------------")
                        print("METRICAS FINAIS DO TESTE DE CARGA (50 USUARIOS CONCORRENTES):")
                        print(f"Total de Requisicoes: {req_count}")
                        print(f"Falhas Tecnicas (5xx): {fail_count} ({fail_rate:.2f}%)")
                        print(f"Latencia Media: {float(avg_latency):.2f} ms")
                        print(f"Latencia Minima: {float(min_latency):.2f} ms")
                        print(f"Latencia Maxima: {float(max_latency):.2f} ms")
                        print(f"Vazao Media (RPS): {float(rps):.2f} req/s")
                        print("----------------------------------------------------------")

    finally:
        print("-> Encerrando servidor FastAPI...")
        server_process.terminate()
        server_process.wait()
        # Limpeza do banco de teste de carga temporário
        if os.path.exists("load_test.db"):
            try:
                os.remove("load_test.db")
            except Exception:
                pass


if __name__ == "__main__":
    main()
