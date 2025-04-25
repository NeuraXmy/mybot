from ..utils import *
import rembg
import numpy as np

SAME_COLOR_THRESHOLD = (10 ** 2) * 3
FLOODFILL_EDGE_COLOR_NUM_RATE_THRESHOLD = 0.6

def color_distance(c1, c2):
    return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2
 

def floodfill(data: np.ndarray, visited: np.ndarray, x: int, y: int, target_color: np.ndarray, replacement_color: np.ndarray) -> None:
    width, height = data.shape[1], data.shape[0]
    stack = [(x, y)]
    while stack:
        x, y = stack.pop()
        if not visited[y, x] and color_distance(data[y, x][:3], target_color[:3]) < SAME_COLOR_THRESHOLD:
            data[y, x] = replacement_color
            visited[y, x] = True
            if x > 0 and not visited[y, x - 1]:
                stack.append((x - 1, y))
            if x < width - 1 and not visited[y, x + 1]:
                stack.append((x + 1, y))
            if y > 0 and not visited[y - 1, x]:
                stack.append((x, y - 1))
            if y < height - 1 and not visited[y + 1, x]:
                stack.append((x, y + 1))


def cutout_img(img: Image.Image, method: str = "adaptive") -> Image.Image:
    img = img.convert("RGBA")
    assert method in ["adaptive", "floodfill", "ai"]
    if method in ['adaptive', 'floodfill']:
        data = np.array(img).reshape(img.size[1], img.size[0], 4).astype(np.int32)
        edge_colors = np.concatenate([
            data[0, :],  # Top row
            data[-1, :],  # Bottom row
            data[:, 0],  # Left column
            data[:, -1]   # Right column
        ], axis=0)
        unique_colors, counts = np.unique(edge_colors, axis=0, return_counts=True)
        first_color = unique_colors[np.argmax(counts)]
        same_pos = [color_distance(first_color, color) < SAME_COLOR_THRESHOLD for color in unique_colors]
        same_num = counts[same_pos].sum()
        total_num = counts.sum()
        if method == "adaptive":
            if same_num / total_num > FLOODFILL_EDGE_COLOR_NUM_RATE_THRESHOLD:
                method = "floodfill"
            else:
                method = "ai"
    
    img = img.convert("RGBA")
    if method == "floodfill":
        data = np.array(img).astype(np.int32)
        visited = np.zeros((data.shape[0], data.shape[1]), dtype=bool)
        for x in range(data.shape[1]):
            for y in range(data.shape[0]):
                if x == 0 or x == data.shape[1] - 1 or y == 0 or y == data.shape[0] - 1:
                    if data[y, x][3] == 0:
                        continue
                    floodfill(data, visited, x, y, np.concatenate([first_color, [255]]), np.array([0, 0, 0, 0]))
        return Image.fromarray(data.astype(np.uint8))

    else:
        data = rembg.remove(img)
        return Image.fromarray(data)
