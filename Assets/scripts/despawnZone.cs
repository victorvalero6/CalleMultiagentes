using UnityEngine;

[RequireComponent(typeof(BoxCollider))]
public class DespawnZone : MonoBehaviour
{
    void Reset()
    {
        // Asegura que sea trigger y tenga el tag correcto
        var bc = GetComponent<BoxCollider>();
        bc.isTrigger = true;
        gameObject.tag = "Despawn";
    }

    void OnTriggerEnter(Collider other)
    {
        // Si el objeto que entra es un vehículo, lo eliminamos
        if (other.CompareTag("Vehicle"))
        {
            Destroy(other.gameObject);
        }
    }
}
