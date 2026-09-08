import perlin_noise

class PerlinNoiseFactory:
    def __init__(self, seed:int, octaves:int):
        self.seed = seed
        self.octaves = octaves
        self.perlin = perlin_noise.PerlinNoise(self.octaves, self.seed)

    def __call__(self, x, y):
        return self.perlin((x, y))

if __name__ == "__main__":
    max_b = -float("inf")
    min_b = float("inf")
    pn = PerlinNoiseFactory(123456789, 1)
    for x in range(1000):
        for y in range(1000):
            r = pn(x/10, y/10)
            if r < min_b:
                min_b = r

            if r > max_b:
                max_b = r

    print(f"max: {max_b}, min: {min_b}")