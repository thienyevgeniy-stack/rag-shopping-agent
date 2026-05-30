package com.example.ragshoppingagent.model

import org.json.JSONObject

data class ProductCard(
    val id: String,
    val name: String,
    val category: String,
    val brand: String,
    val price: Double,
    val imageUrl: String,
    val detailUrl: String,
    val reason: String,
) {
    companion object {
        fun fromJson(json: JSONObject): ProductCard {
            return ProductCard(
                id = json.optString("id"),
                name = json.optString("name"),
                category = json.optString("category"),
                brand = json.optString("brand"),
                price = json.optDouble("price"),
                imageUrl = json.optString("image_url"),
                detailUrl = json.optString("detail_url"),
                reason = json.optString("reason"),
            )
        }
    }
}
