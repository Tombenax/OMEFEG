import perlin_noise

class PerlinNoiseFactory:
    def __init__(self, seed:int, octaves:int):
        self.seed = seed
        self.octaves = octaves
        self.perlin = perlin_noise.PerlinNoise(self.octaves, self.seed)

    def __call__(self, x, y):
        return self.perlin((x, y))

if __name__ == "__main__":
    def generate_heightmap(noise, width, depth, N, scale=10):
        # Generate all noise values
        values = []
        for x in range(width):
            for z in range(depth):
                values.append(noise([x / scale, z / scale]))

        # Sort values to find percentile thresholds
        sorted_values = sorted(values)

        # Calculate thresholds
        thresholds = [
            sorted_values[int(len(sorted_values) * i / N)]
            for i in range(1, N)
        ]

        # Convert noise values to discrete heights
        heightmap = []

        for x in range(width):
            row = []

            for z in range(depth):
                value = noise([x / scale, z / scale])

                height = 0
                while height < len(thresholds) and value >= thresholds[height]:
                    height += 1

                row.append(height)

            heightmap.append(row)

        return heightmap

    from perlin_noise import PerlinNoise

    noise = PerlinNoise(octaves=3)

    heightmap = generate_heightmap(
        noise,
        width=100,
        depth=100,
        N=3,
        scale=20
    )

    for x in range(1000):
        for y in range(1000):
            print(heightmap[x][y])




