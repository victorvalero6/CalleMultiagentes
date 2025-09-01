using UnityEngine;

public class VehicleSpawner : MonoBehaviour
{
    [Header("Prefabs de vehículo (agrega varios)")]
    public GameObject[] vehiclePrefabs;

    [Tooltip("Pesos relativos por prefab (opcional). Si se deja vacío o con tamaños distintos, se ignora y se asume uniforme.")]
    public float[] prefabWeights;

    [Header("Spawns (empties en la escena)")]
    public Transform[] spawnPoints;

    [Header("Opciones")]
    public float spawnInterval = 3f;   // segundos entre spawns
    public int maxVehicles = 20;       // máximo de autos activos

    private int vehicleCount = 0;

    void Start()
    {
        InvokeRepeating(nameof(SpawnVehicle), 1f, spawnInterval);
    }

    void SpawnVehicle()
    {
        if (vehiclePrefabs == null || vehiclePrefabs.Length == 0) return;
        if (spawnPoints == null || spawnPoints.Length == 0) return;
        if (vehicleCount >= maxVehicles) return;

        // 1) Elegir spawn
        Transform spawn = spawnPoints[Random.Range(0, spawnPoints.Length)];

        // 2) Elegir prefab (uniforme o con pesos)
        GameObject prefab = PickPrefab();

        // 3) Instanciar
        GameObject car = Instantiate(prefab, spawn.position, spawn.rotation);

        // Asegura tag para el Despawn
        car.tag = "Vehicle";

        vehicleCount++;

        // Aviso al destruirse
        var tracker = car.GetComponent<DespawnTracker>();
        if (tracker == null) tracker = car.AddComponent<DespawnTracker>();
        tracker.Init(this);
    }

    GameObject PickPrefab()
    {
        if (prefabWeights != null && prefabWeights.Length == vehiclePrefabs.Length)
        {
            float sum = 0f;
            for (int i = 0; i < prefabWeights.Length; i++)
                sum += Mathf.Max(0f, prefabWeights[i]);

            if (sum > 0f)
            {
                float r = Random.Range(0f, sum);
                float acc = 0f;
                for (int i = 0; i < vehiclePrefabs.Length; i++)
                {
                    acc += Mathf.Max(0f, prefabWeights[i]);
                    if (r <= acc) return vehiclePrefabs[i];
                }
            }
        }
        // Fallback: uniforme
        return vehiclePrefabs[Random.Range(0, vehiclePrefabs.Length)];
    }

    public void NotifyDespawn()
    {
        vehicleCount = Mathf.Max(0, vehicleCount - 1);
    }
}

public class DespawnTracker : MonoBehaviour
{
    private VehicleSpawner spawner;

    public void Init(VehicleSpawner s) { spawner = s; }

    void OnDestroy()
    {
        if (spawner != null) spawner.NotifyDespawn();
    }
}
