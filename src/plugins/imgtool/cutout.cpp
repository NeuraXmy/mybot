/*
从文件读入二进制形式的图片数据，输出二进制形式抠完的图
参数1: 文件名:str 参数2: 输出文件名:str 参数3: 容差:int
输入文件格式: n:int, h:int, w:int, r00:uint8_t g00:uint8_t b00:uint8_t, a00:uint8_t, ...
*/

#include <iostream>
#include <unordered_map>
#include <vector>
#include <string>
#include <cstdio>
#include <tuple>
#include <cassert>  

constexpr int dx[4] = {0, 0, -1, 1};
constexpr int dy[4] = {-1, 1, 0, 0};

union Color {
    struct {
        uint8_t r;
        uint8_t g;
        uint8_t b;
        uint8_t a;
    };
    uint32_t key;
    Color() = default;
    Color(uint8_t r, uint8_t g, uint8_t b, uint8_t a) : r(r), g(g), b(b), a(a) {}
    Color(uint32_t key) : key(key) {}
};

int n, h, w;
Color *img = nullptr;

Color& get_color(int t, int y, int x) {
    return img[t * h * w + y * w + x];
}
int quad(int x) {
    return x * x;
}
int color_diff(const Color& a, const Color& b) {
    return quad(int(a.r) - int(b.r)) + quad(int(a.g) - int(b.g)) + quad(int(a.b) - int(b.b));
}
bool check_pos(int y, int x) {
    return y >= 0 && y < h && x >= 0 && x < w;
}

void floodfill(int t, int sy, int sx, const Color& src, const Color& dst, int tolerance) {
    assert(!dst.a);
    static std::vector<std::tuple<int, int>> stack;
    stack.clear();
    stack.emplace_back(sy, sx);
    get_color(t, sy, sx) = dst;

    // std::cerr << "[cutout] start floodfill (" << t << ", " << sy << ", " << sx << ")" << std::endl;

    while (!stack.empty()) {
        auto [y, x] = stack.back();
        stack.pop_back();

        // std::cerr << "[cutout] floodfill (" << t << ", " << y << ", " << x << ")" << std::endl;
        
        for (int i = 0; i < 4; ++i) {
            int ny = y + dy[i];
            int nx = x + dx[i];
            if (!check_pos(ny, nx)) continue;
            auto& c = get_color(t, ny, nx);
            if (!c.a) continue;
            if (color_diff(c, src) > tolerance) continue;
            c = dst;
            stack.emplace_back(ny, nx);
        }
    }
}


int main(int argc, char *argv[]) {
    std::string filename = argv[1];
    std::string outname = argv[2];
    int tolerance = atoi(argv[3]);
    tolerance = (tolerance * tolerance) * 3;
    
    // 读取图片数据
    FILE *fp = fopen(filename.c_str(), "rb");
    if (!fp) {
        std::cerr << "[cutout] error opening file: " << filename << std::endl;
        return 1;
    }
    fread(&n, sizeof(int), 1, fp);
    fread(&h, sizeof(int), 1, fp);
    fread(&w, sizeof(int), 1, fp);
    long long size = n * h * w * sizeof(Color);
    if (size > 1e9) {
        std::cerr << "[cutout] error: image size too large" << std::endl;
        fclose(fp);
        return 1;
    }
    img = new Color[n * h * w];
    auto read = fread(img, sizeof(Color), n * h * w, fp);
    assert(read == n * h * w);
    fclose(fp);

    std::cerr << "[cutout] start to cutout img (" << n << "x" << h << "x" << w << ")" << std::endl;
    
    // 以第一帧的边缘像素作为参照，找出最常见的颜色
    std::unordered_map<uint32_t, int> edge_color_count{};
    Color max_color;
    int max_color_count = 0;

    auto update_color = [&](Color c) {
        int cnt = ++edge_color_count[c.key];
        if (cnt > max_color_count) {
            max_color_count = cnt;
            max_color = c;
        }
    };

    for (int y = 0; y < h; ++y) { 
        update_color(get_color(0, y, 0));
        update_color(get_color(0, y, w - 1));
    }
    for (int x = 0; x < w; ++x) {
        update_color(get_color(0, 0, x));
        update_color(get_color(0, h - 1, x));
    }

    std::cerr << "[cutout] max color: " << int(max_color.r) << " " << int(max_color.g) << " " << int(max_color.b) << " " << int(max_color.a) << std::endl;

    // 遍历每一帧，从边缘开始抠图
    for (int t = 0; t < n; ++t) {
        for (int y = 0; y < h; ++y) {
            for (int x = 0; x < w; ++x) {
                if (x == 0 || x == w - 1 || y == 0 || y == h - 1) {
                    auto& c = get_color(t, y, x);
                    if (c.a && color_diff(c, max_color) <= tolerance) 
                        floodfill(t, y, x, max_color, Color(0, 0, 0, 0), tolerance);
                }
            }
        }
    }

    std::cerr << "[cutout] cutout done" << std::endl;

    // 输出抠完的图
    FILE *out_fp = fopen(outname.c_str(), "wb");
    if (!out_fp) {
        std::cerr << "[cutout] error opening output file: " << outname << std::endl;
        delete[] img;
        return 1;
    }
    fwrite(img, sizeof(Color), n * h * w, out_fp);
    fclose(out_fp);
    delete[] img;
    return 0;
}