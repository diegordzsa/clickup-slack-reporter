"""
Script de diagnóstico: muestra todos los status únicos que aparecen
en las tasks de cada carpeta, con conteo de cuántas tasks hay en cada uno.
Esto nos ayuda a identificar qué status cuenta como "entregado".
"""
from collections import Counter
from clickup_client import get_tasks_from_folder
from config import FOLDERS


def diagnose():
    print("🔍 Diagnóstico de status por carpeta\n")
    print("=" * 60)

    for client_name, folder_id in FOLDERS.items():
        print(f"\n📁 {client_name} (ID: {folder_id})")
        print("-" * 60)

        tasks = get_tasks_from_folder(folder_id)
        print(f"Total de tasks: {len(tasks)}\n")

        # Contar tasks por status
        status_counter = Counter()
        for task in tasks:
            status = task.get("status", {}).get("status", "SIN_STATUS")
            status_counter[status] += 1

        # Mostrar status ordenados de más a menos comunes
        print(f"Status encontrados ({len(status_counter)} únicos):")
        for status, count in status_counter.most_common():
            print(f"   • '{status}' → {count} tasks")

        # También mostrar los assignees únicos para ir viendo el equipo
        assignee_counter = Counter()
        for task in tasks:
            assignees = task.get("assignees", [])
            if not assignees:
                assignee_counter["SIN ASIGNAR"] += 1
            else:
                for a in assignees:
                    name = a.get("username", "?")
                    assignee_counter[name] += 1

        print(f"\nAssignees encontrados ({len(assignee_counter)} únicos):")
        for assignee, count in assignee_counter.most_common():
            print(f"   • {assignee} → {count} tasks asignadas")

    print("\n" + "=" * 60)
    print("✅ Diagnóstico completo")


if __name__ == "__main__":
    diagnose()