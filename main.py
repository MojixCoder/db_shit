import os
from random import randint

import aiofiles
import psycopg
import uvicorn
from fastapi import FastAPI, UploadFile, Path, Form, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response


app = FastAPI()

app.mount("/files", StaticFiles(directory="files"), name="files")


db_conn = psycopg.connect("dbname=food_service user=postgres password=postgres host=localhost port=5432")


@app.on_event("shutdown")
def shutdown_event():
    db_conn.close()



##### Restaurant APIs #####

@app.get("/api/restaurants")
async def restaurants():
    response = []
    with db_conn.cursor() as cur:
        res = cur.execute("""
            SELECT id, name, address, image
            FROM restaurants;
        """)
        for row in cur.fetchall():
            record = {
                "id": row[0],
                "name": row[1].strip(),
                "address": row[2].strip(),
                "image": row[3].strip(),
            }
            response.append(record)
    return response


@app.post("/api/restaurants")
async def create_restaurant(
    name: str = Form(...), 
    address: str = Form(...), 
    image: UploadFile = File(...),
):
    inserted_id: int
    with db_conn.cursor() as cur:
        file_path = await save_file(image)
        res = cur.execute("""
            INSERT INTO restaurants (name, address, image) VALUES (%s, %s, %s) RETURNING id;
        """, (name.strip(), address.strip(), file_path.strip()))
        inserted_id = res.fetchone()[0]
        db_conn.commit()
    
    response = {
        "id": inserted_id,
        "name": name,
        "address": address,
        "image": f"http://localhost:8080/{file_path}",
    }

    return JSONResponse(response, status_code=201)


@app.get("/api/restaurants/{id}")
async def get_restaurant(id: int):
    response = {}
    with db_conn.cursor() as cur:
        res = cur.execute("""
            SELECT id, name, address, image FROM restaurants
            WHERE id = %s;
            """, (id,))
        record = res.fetchone()
        if record is None:
            return JSONResponse({"detail": "not found"}, status_code=404)
        else:
            response["id"] = record[0]
            response["name"] = record[1].strip()
            response["address"] = record[2].strip()
            response["image"] = record[3].strip()
       
    return JSONResponse(response)


@app.delete("/api/restaurants/{id}")
async def delete_restaurant(id: int):
    with db_conn.cursor() as cur:
        exists = cur.execute("""
            SELECT id FROM restaurants
            WHERE id = %s;
            """, (id,))
        exists = exists.fetchone() is not None
        if exists:
            cur.execute("""
            DELETE FROM restaurants
            WHERE id = %s;
            """, (id,))
            db_conn.commit()
        else:
            return JSONResponse({"detail": "not found"}, status_code=404)
    return Response(status_code=204)


@app.put("/api/restaurants/{id}")
async def update_restaurant(
    id: int = Path(...),
    name: str = Form(...), 
    address: str = Form(...), 
    image: UploadFile = File(...),
):
    file_path = ""
    with db_conn.cursor() as cur:
        exists = cur.execute("""
            SELECT id FROM restaurants
            WHERE id = %s;
        """, (id,))
        if exists.fetchone() is None:
            return JSONResponse({"detail": "not found"}, status_code=404)

        file_path = await save_file(image)
        cur.execute("""
            UPDATE restaurants
            SET name = %s, address = %s, image = %s
            WHERE id = %s
        """, (name.strip(), address.strip(), file_path, id))
        db_conn.commit()
    
    response = {
        "id": id,
        "name": name,
        "address": address,
        "image": file_path,
    }

    return response



##### Food APIs #####

@app.get("/api/restaurants/{id}/foods")
async def restaurant_foods(id: int):
    response = []
    with db_conn.cursor() as cur:
        res = cur.execute("""
        SELECT 
            foods.id food_id,
            foods.name food_name,
            foods.recipe food_recipe,
            foods.image food_image,
            restaurants.id restaurant_id,
            restaurants.name restaurant_name,
            restaurants.image restaurant_image,
        FROM foods INNER JOIN restaurants ON foods.restaurant_id = restaurants.id
        WHERE foods.restaurant_id = %s;
        """, (id,))
        for row in res.fetchall():
            record = {
                "food_id": row[0],
                "food_name": row[1].strip(),
                "food_recipe": row[2].strip(),
                "food_image": row[3].strip(),
                "restaurant_id": row[4],
                "restaurant_name": row[5].strip(),
                "restaurant_image": row[6].strip(),
            }
            response.append(record)
        
        return response


@app.post("/api/restaurants/{id}/foods")
async def create_food(
    id: int = Path(...),
    name: str = Form(...), 
    recipe: str = Form(...), 
    image: UploadFile = File(...),
):
    file_path = ""
    inserted_id = 0
    with db_conn.cursor() as cur:
        exists = cur.execute("""
            SELECT id FROM restaurants
            WHERE id = %s;
        """, (id,))
        if exists.fetchone() is None:
            return JSONResponse({"detail": "not found"}, status_code=404)
        
        file_path = await save_file(image)
        res = cur.execute("""
            INSERT INTO foods (name, recipe, image, restaurant_id) VALUES (%s, %s, %s, %s) RETURNING id;
        """, (name.strip(), recipe.strip(), file_path, id))
        inserted_id = res.fetchone()[0]
        db_conn.commit()

    response = {
        "id": inserted_id,
        "restaurant_id": id,
        "name": name,
        "recipe": recipe,
        "image": file_path,
    }

    return JSONResponse(response, status_code=201)

@app.get("/api/foods/{id}")
async def get_food(id: int):
    response = {}
    with db_conn.cursor() as cur:
        res = cur.execute("""
        SELECT 
            foods.id food_id,
            foods.name food_name,
            foods.recipe food_recipe,
            foods.image food_image,
            restaurants.id restaurant_id,
            restaurants.name restaurant_name,
            restaurants.image restaurant_image
        FROM foods INNER JOIN restaurants ON foods.restaurant_id = restaurants.id
        WHERE foods.id = %s;
        """, (id,))
        record = res.fetchone()

        if record is None:
            return JSONResponse({"detail": "not found"}, status_code=404)
        else:
            res = cur.execute("""
                SELECT id, name, value
                FROM ingredients
                WHERE food_id = %s
            """, (record[0],))
            ingredients = []
            for row in res.fetchall():
                ingredient = {
                    "id": row[0],
                    "name": row[1].strip(),
                    "value": row[2].strip(),
                }
                ingredients.append(ingredient)

            response = {
                "food_id": record[0],
                "food_name": record[1].strip(),
                "food_recipe": record[2].strip(),
                "food_image": record[3].strip(),
                "restaurant_id": record[4],
                "restaurant_name": record[5].strip(),
                "restaurant_image": record[6].strip(),
                "ingredients": ingredients,
            }
    return response

@app.delete("/api/foods/{id}")
async def delete_food(id: int):
    with db_conn.cursor() as cur:
        exists = cur.execute("""
            SELECT id FROM foods
            WHERE id = %s;
            """, (id,))
        exists = exists.fetchone() is not None
        if exists:
            cur.execute("""
            DELETE FROM foods
            WHERE id = %s;
            """, (id,))
            db_conn.commit()
        else:
            return JSONResponse({"detail": "not found"}, status_code=404)
    return Response(status_code=204)


@app.put("/api/foods/{id}")
async def update_food(
    id: int = Path(...),
    name: str = Form(...), 
    recipe: str = Form(...), 
    image: UploadFile = File(...),
):
    file_path = ""
    with db_conn.cursor() as cur:
        exists = cur.execute("""
            SELECT id FROM foods
            WHERE id = %s;
        """, (id,))
        if exists.fetchone() is None:
            return JSONResponse({"detail": "not found"}, status_code=404)

        file_path = await save_file(image)
        cur.execute("""
            UPDATE foods
            SET name = %s, recipe = %s, image = %s
            WHERE id = %s
        """, (name.strip(), recipe.strip(), file_path, id))
        db_conn.commit()
    
    response = {
        "id": id,
        "name": name,
        "recipe": recipe,
        "image": file_path,
    }

    return response


##### Ingredient APIs #####

@app.get("/api/ingredients/{id}")
async def get_ingredient(id: int):
    response = {}
    with db_conn.cursor() as cur:
        res = cur.execute("""
        SELECT
            foods.id food_id,
            foods.name food_name,
            foods.recipe food_recipe,
            foods.image food_image,
            ingredients.id ingredient_id,
            ingredients.name ingredient_name,
            ingredients.value ingredient_value 
        FROM foods INNER JOIN ingredients ON foods.ID = ingredients.food_id
        WHERE ingredients.id = %s;
        """, (id,))
        record = res.fetchone()

        if record is None:
            return JSONResponse({"detail": "not found"}, status_code=404)

    response = {
        "food_id": record[0],
        "food_name": record[1].strip(),
        "food_recipe": record[2].strip(),
        "food_image": record[3].strip(),
        "ingredient_id": record[4],
        "ingredient_name": record[5].strip(),
        "ingredient_value": record[6].strip(),
    }

    return response


@app.post("/api/foods/{id}/ingredients")
async def create_ingredient(
    id: int = Path(...),
    name: str = Form(...), 
    value: str = Form(...), 
):
    inserted_id = 0
    with db_conn.cursor() as cur:
        exists = cur.execute("""
            SELECT id FROM foods
            WHERE id = %s;
        """, (id,))
        if exists.fetchone() is None:
            return JSONResponse({"detail": "not found"}, status_code=404)
        
        res = cur.execute("""
            INSERT INTO ingredients (name, value, food_id) VALUES (%s, %s, %s) RETURNING id;
        """, (name.strip(), value.strip(), id))
        inserted_id = res.fetchone()[0]
        db_conn.commit()

    response = {
        "id": inserted_id,
        "food_id": id,
        "name": name,
        "value": value,
    }

    return JSONResponse(response, status_code=201)
    

async def save_file(upload_file: UploadFile) -> str:
    random_number = randint(1, 10000000)
    file_path = os.path.join("files", f"{random_number}-{upload_file.filename}")
    async with aiofiles.open(file_path, "wb") as out_file:
        content = await upload_file.read()  
        await out_file.write(content)  
    return file_path


if __name__ == "__main__":
    uvicorn.run(app=app, host="0.0.0.0", port=8080, debug=True)
