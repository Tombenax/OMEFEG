import numpy as np
import pickle

class NeuralNetwork:
    def __init__(self, input_neurons:int, hidden_neurons:list[int], output_neurons:int, activaction_functions:list, derivative_activation_functions:list, hidden_layers_count:int=1):
        self.hidden_layers_count = hidden_layers_count
        self.input_layer = np.zeros(input_neurons)
        self.hidden_layers = []
        self.weights = []
        self.biases = []
        self.activaction_functions = activaction_functions
        self.hidden_neurons = hidden_neurons
        self.input_neurons = input_neurons
        self.output_neurons = output_neurons
        self.derivative_activation_functions = derivative_activation_functions
        if len(hidden_neurons) != hidden_layers_count:
            raise TypeError("hidden_neurons and hidden_layers_count must match!!!")
        
        self.unkonwn_variable = []
        self.unkonwn_variable.append(input_neurons)
        self.unkonwn_variable.extend(hidden_neurons)
        self.unkonwn_variable.append(output_neurons)

        for hidden in range(hidden_layers_count):
            self.hidden_layers.append(np.zeros(hidden_neurons[hidden]))

        for i in range(len(self.unkonwn_variable)-1):
            inp = self.unkonwn_variable[i]
            out = self.unkonwn_variable[i+1]

            self.weights.append(np.random.randn(out, inp) * np.sqrt(2/inp))
            self.biases.append(np.zeros((out, 1)))
        
        self.output_layer = np.zeros(output_neurons)

    def encode_Y(self, Y):
        one_hot = np.zeros((self.output_neurons, Y.size))
        one_hot[Y, np.arange(Y.size)] = 1
        return one_hot

    def forwardpass(self, X):
        self.Zs = []
        self.As = [X]

        A = self.As[0]

        for i in range(len(self.weights)):
            Z = self.weights[i] @ A + self.biases[i]
            self.Zs.append(Z)

            A = self.activaction_functions[i](Z)
            self.As.append(A)

        return A

    def calculate_errors(self, Y):
        Y = self.encode_Y(Y)

        L = len(self.weights)

        dWs = [None] * L
        dBs = [None] * L

        # ---------- OUTPUT LAYER ----------

        if self.activaction_functions[-1] == softmax:
            # Cross Entropy + Softmax
            dZ = self.As[-1] - Y
        else:
            dA = self.As[-1] - Y
            dZ = dA * self.derivative_activation_functions[-1](self.Zs[-1])

        m = Y.shape[1]

        dWs[-1] = (dZ @ self.As[-2].T) / m
        dBs[-1] = np.sum(dZ, axis=1, keepdims=True) / m

        # ---------- HIDDEN LAYERS ----------

        for l in range(L - 2, -1, -1):
            dZ = self.weights[l + 1].T @ dZ
            dZ *= self.derivative_activation_functions[l](self.Zs[l])

            dWs[l] = (dZ @ self.As[l].T) / m
            dBs[l] = np.sum(dZ, axis=1, keepdims=True) / m

        return dWs, dBs
    
    def backprop(self, Y, alpha):
        dWs, dBs = self.calculate_errors(Y)

        for i in range(len(self.weights)):
            self.weights[i] -= alpha * dWs[i]
            self.biases[i] -= alpha * dBs[i]

    def get_predictions(self):
        return np.argmax(self.As[-1], 0)

    def get_accuracy(self, predictions, Y):
        print(predictions, Y)
        return np.sum(predictions == Y) / Y.size

    def train(self, inputs, labels, epochs, alpha):
        for i in range(epochs):
            indices = np.random.permutation(inputs.shape[1])
            inputs = inputs[:, indices]
            labels = labels[indices]

            print(f"Epoch {i} starting")
            self.forwardpass(inputs)
            self.backprop(labels, alpha)

            print(f"Epoch {i} ending")
            if i % 5 == 0:
                with open("checkpoint.pkl", "wb") as f:
                    data = {
                        "weights":self.weights,
                        "biases":self.biases,
                        "epoch":i
                    }
                    pickle.dump(data, f)

                self.forwardpass(inputs)
                print("Accuracy:", self.get_accuracy(self.get_predictions(), labels))
            

        
if __name__ == "__main__":

    from wakepy import keep

    def ReLU(X):
        return np.maximum(0, X)
    
    def derReLU(X):
        return (X > 0).astype(float)

    def softmax(X):
        X = X - np.max(X, axis=0, keepdims=True)
        exp = np.exp(X)
        return exp / np.sum(exp, axis=0, keepdims=True)

    def dersoftmax(x):
        s = softmax(x).reshape(-1, 1)
        return np.diagflat(s) - s @ s.T
    
    def Nothing(X):
        return X
        

    from sklearn.datasets import fetch_openml
    mnist = fetch_openml("mnist_784", version=1, as_frame=False)

    X = mnist.data.astype(np.float32) / 255.0
    Y = mnist.target.astype(int)

    X = X.T

    nn = NeuralNetwork(784, [20, 20], 10, [ReLU, ReLU, softmax], [derReLU, derReLU, dersoftmax], 2)
    train_epochs = 200000
    alpha = 0.001
    cnt = input("Do you want to reload previous weights and biases? (y/n)\n").lower()
    if cnt == "n":
        try:
            with keep.running():
                nn.train(X, Y, train_epochs, alpha)
        except KeyboardInterrupt:
            pass
    elif cnt == "y":
        cnt = input("Do you want to restart session from previous w and bs? (y/n)\n").lower()
        with open("checkpoint.pkl", "rb") as f:
            content = pickle.load(f)
            nn.weights = content["weights"]
            nn.biases = content["biases"]
            prev_epoch = content["epoch"]
        if cnt == "y":
            with keep.running():
                try:
                    nn.train(X, Y, train_epochs-prev_epoch, alpha)
                except KeyboardInterrupt:
                    pass


    import pygame
    import numpy as np

    # MNIST resolution
    WIDTH = 28
    HEIGHT = 28
    SCALE = 1  # Makes the window 560x560

    pygame.init()

    screen = pygame.display.set_mode((WIDTH * SCALE, HEIGHT * SCALE))
    pygame.display.set_caption("Draw a digit - Press Enter to Predict")

    canvas = np.zeros((HEIGHT, WIDTH), dtype=np.float32)

    drawing = False
    running = True

    while running:
        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:

                # Clear
                if event.key == pygame.K_c:
                    canvas.fill(0)

                # Predict
                elif event.key == pygame.K_RETURN:

                    X = canvas.reshape(-1, 1)

                    output = nn.forwardpass(X)

                    prediction = np.argmax(output)

                    print("----------------------")
                    print("Prediction:", prediction)
                    print("Network output:")
                    print(output.ravel())

            elif event.type == pygame.MOUSEBUTTONDOWN:
                drawing = True

            elif event.type == pygame.MOUSEBUTTONUP:
                drawing = False

        if drawing:
            mx, my = pygame.mouse.get_pos()

            x = mx // SCALE
            y = my // SCALE

            # Draw a small brush
            for dy in range(-1, 2):
                for dx in range(-1, 2):

                    xx = x + dx
                    yy = y + dy

                    if 0 <= xx < WIDTH and 0 <= yy < HEIGHT:
                        canvas[yy, xx] = 1.0

        screen.fill((0, 0, 0))

        for y in range(HEIGHT):
            for x in range(WIDTH):

                color = int(canvas[y, x] * 255)

                pygame.draw.rect(
                    screen,
                    (color, color, color),
                    (x * SCALE, y * SCALE, SCALE, SCALE),
                )

        pygame.display.flip()

    pygame.quit()