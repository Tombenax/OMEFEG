#THIS CODE IS ME FOLLOWING THE TUTORIAL HERE(and all of the other videos in the tutorial):
#https://www.youtube.com/watch?v=W3Z9Bcy--vM&list=PLn3eTxaOtL2M4qgHpHuxY821C_oX0GvM7&


from vulkan import *
import glfw

import time

import numpy as np
import pyrr

def supported(extensions, layers):
    supportedExtensions = [extension.extensionName for extension in vkEnumerateInstanceExtensionProperties(None)]

    for i in supportedExtensions:
        print(f"{i} is a supported extension")

    for extension in extensions:
        if extension in supportedExtensions:
            print(f"\"{extension}\" is supported")
        else:
            print(f"\"{extension}\" is not supported")

    supportedLayer = [layer.layerName for layer in vkEnumerateInstanceLayerProperties()]

    for i in supportedLayer:
        print(f"{i} is a supported layer")

    for layer in layers:
        if layer in supportedLayer:
            print(f"\"{layer}\" is supported")
        else:
            print(f"\"{layer}\" is not supported")


def make_instance():
    version = vkEnumerateInstanceVersion()

    appInfo = VkApplicationInfo(
        pApplicationName = "Vulkan Test",
        applicationVersion = version,
        pEngineName = "Doing it the hard way",
        engineVersion = version,
        apiVersion = version
    )

    extensions = glfw.get_required_instance_extensions()

    layers = []
    supported(extensions, layers)

    createInfo = VkInstanceCreateInfo(
        pApplicationInfo = appInfo,
        enabledLayerCount = 0, ppEnabledLayerNames = None,
        enabledExtensionCount = len(extensions), ppEnabledExtensionNames = extensions
    )

    try:
        return vkCreateInstance(createInfo, None)
    except error as e:
        print(e)
        return None

def choose_physical_device(instance):
    availableDevices = vkEnumeratePhysicalDevices(instance)

    print(f"There are {len(availableDevices)} physical devices")

    for device in availableDevices:
        log_device_properties(device)
        if is_suitable(device):
            return device

    return None

def log_device_properties(device):

    properties = vkGetPhysicalDeviceProperties(device)

    print(f"Device name: {properties.deviceName}")

    print("Device type: ", end="")

    if properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_CPU:
        print("CPU")
    elif properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU:
        print("Discrete GPU")
    elif properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU:
        print("Integrated GPU")
    elif properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_VIRTUAL_GPU:
        print("Virtual GPU")
    else:
        print("WTF do you have?!?!?!")

def is_suitable(device):

    requestedExtensions = [VK_KHR_SWAPCHAIN_EXTENSION_NAME]

    return check_device_extension_support(device, requestedExtensions)

def check_device_extension_support(device, requestedExtensions):

    supportedExtensions = [extension.extensionName for extension in vkEnumerateDeviceExtensionProperties(device, None)]

    for extension in requestedExtensions:
        if extension not in supportedExtensions:
            return False
    
    return True


def make_device(instance, surface, width, height):
    physicalDevice = choose_physical_device(instance)
    device = create_logical_device(physicalDevice, instance, surface)
    graphicsQueue, presentQueue = get_queues(physicalDevice, device, instance, surface)
    bundle = create_swapchain(instance, device, physicalDevice, surface, width, height)

    

    return physicalDevice, device, graphicsQueue, presentQueue, bundle.swapchain, bundle.frames, bundle.format, bundle.extent, len(bundle.frames), 0

class QueueFamilyIndices:
    def __init__(self):
        self.graphicsFamily = None
        self.presentFamily = None
    
    def is_complete(self):
        return not(self.graphicsFamily is None or self.presentFamily is None)

class SwapChainSupportDetails:
    def __init__(self):
        self.capabilities = None
        self.format = None
        self.presentModes = None

class SwapChainFrame:
    def __init__(self):
        self.image = None
        self.image_view = None
        self.framebuffer = None
        self.commandbuffer = None
        self.inFlight = None
        self.imageAvailable = None
        self.renderFinished = None

class SwapChainBundle:
    def __init__(self):
        self.swapchain = None
        self.frames = []
        self.format = None
        self.extent = None

class FramebufferInput:
    def __init__(self):
        self.device = None
        self.renderpass = None
        self.swapchainExtent = None

def find_queue_families(device, instance, surface):
    indices = QueueFamilyIndices()

    queueFamiles = vkGetPhysicalDeviceQueueFamilyProperties(device)

    print(f"There are {len(queueFamiles)} queue families available on the system")

    for i, queueFamily in enumerate(queueFamiles):

        if queueFamily.queueFlags & VK_QUEUE_GRAPHICS_BIT:
            indices.graphicsFamily = i

        if vkGetInstanceProcAddr(instance, "vkGetPhysicalDeviceSurfaceSupportKHR")(device, i, surface):
            indices.presentFamily = i

        if indices.is_complete():
            break

    return indices

def create_logical_device(physicalDevice, instance, surface):

    indices = find_queue_families(physicalDevice, instance, surface)

    uniqueIndices = [indices.graphicsFamily]
    if indices.graphicsFamily != indices.presentFamily:
        uniqueIndices.append(indices.presentFamily)

    queueCreateInfo = []
    
    for queueFamilyIndex in uniqueIndices:
        queueCreateInfo.append(VkDeviceQueueCreateInfo(queueFamilyIndex=queueFamilyIndex, queueCount=1, pQueuePriorities = [1.0,]))

    deviceFeatures = VkPhysicalDeviceFeatures()

    enabledLayers = []

    deviceExtensions = [
        VK_KHR_SWAPCHAIN_EXTENSION_NAME,
    ]

    createInfo = VkDeviceCreateInfo(
        queueCreateInfoCount = len(queueCreateInfo),
        pQueueCreateInfos = queueCreateInfo,
        enabledExtensionCount = len(deviceExtensions),
        ppEnabledExtensionNames = deviceExtensions,
        pEnabledFeatures = [deviceFeatures,],
        enabledLayerCount = len(enabledLayers), ppEnabledLayerNames = enabledLayers
    )

    return vkCreateDevice(physicalDevice = physicalDevice, pCreateInfo = [createInfo,], pAllocator = None)

def get_queues(physicalDevice, device, instance, surface):
    indices = find_queue_families(physicalDevice, instance, surface)

    return [
        vkGetDeviceQueue(
            device = device,
            queueFamilyIndex = indices.graphicsFamily,
            queueIndex = 0
        ),
        vkGetDeviceQueue(
            device = device,
            queueFamilyIndex = indices.presentFamily,
            queueIndex = 0
        )
    ]

def query_swapchain_support(instance, physicalDevice, surface):

    support = SwapChainSupportDetails()

    vkGetPhysicalDeviceSurfaceCapabilitiesKHR = vkGetInstanceProcAddr(instance, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR")
    support.capabilities = vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physicalDevice, surface)
    
    support.formats = vkGetInstanceProcAddr(instance, "vkGetPhysicalDeviceSurfaceFormatsKHR")(physicalDevice, surface)

    support.presentModes = vkGetInstanceProcAddr(instance, "vkGetPhysicalDeviceSurfacePresentModesKHR")(physicalDevice, surface)

    return support

def choose_swapchain_surface_format(formats):

    for format in formats:
        if format.format == VK_FORMAT_B8G8R8A8_UNORM and format.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR:
            return format
    
    return formats[0]

def choose_swapchain_present_mode(presentModes):

    for presentMode in presentModes:
        if presentMode == VK_PRESENT_MODE_MAILBOX_KHR:
            print("Using present mode 'Mailbox'")
            return presentMode

    print("Using present mode 'FIFO'")
    return VK_PRESENT_MODE_FIFO_KHR

def choose_swapchain_extent(width, height, capabilities):

    extent = VkExtent2D(width, height)

    extent.width = min(
        capabilities.maxImageExtent.width,
        max(capabilities.minImageExtent.width, extent.width)
    )

    extent.height = min(
        capabilities.maxImageExtent.height,
        max(capabilities.minImageExtent.height, extent.height)
    )

    return extent

def create_swapchain(instance, logicalDevice, physicalDevice, surface, width, height):

    support = query_swapchain_support(instance, physicalDevice, surface)

    format = choose_swapchain_surface_format(support.formats)

    presentMode = choose_swapchain_present_mode(support.presentModes)

    extent = choose_swapchain_extent(width, height, support.capabilities)

    imageCount = min(support.capabilities.maxImageCount, support.capabilities.minImageCount + 1)

    indices = find_queue_families(physicalDevice, instance, surface)
    queueFamilyIndices = [
        indices.graphicsFamily, indices.presentFamily
    ]
    if indices.graphicsFamily != indices.presentFamily:
        imageSharingMode = VK_SHARING_MODE_CONCURRENT
        queueFamilyIndexCount = 2
        pQueueFamilyIndices = queueFamilyIndices
    else:
        imageSharingMode = VK_SHARING_MODE_EXCLUSIVE
        queueFamilyIndexCount = 0
        pQueueFamilyIndices = None

    createInfo = VkSwapchainCreateInfoKHR(surface = surface, minImageCount = imageCount, imageFormat = format.format, imageColorSpace = format.colorSpace, imageExtent = extent, imageArrayLayers = 1, imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT, imageSharingMode = imageSharingMode, queueFamilyIndexCount = queueFamilyIndexCount, pQueueFamilyIndices = queueFamilyIndices, preTransform = support.capabilities.currentTransform, compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR, presentMode = presentMode, clipped = VK_TRUE)

    bundle = SwapChainBundle()

    bundle.swapchain = vkGetDeviceProcAddr(logicalDevice, "vkCreateSwapchainKHR")(logicalDevice, createInfo, None)
    
    images = vkGetDeviceProcAddr(logicalDevice, "vkGetSwapchainImagesKHR")(logicalDevice, bundle.swapchain)

    for image in images:

        components = VkComponentMapping(
            r = VK_COMPONENT_SWIZZLE_IDENTITY,
            g = VK_COMPONENT_SWIZZLE_IDENTITY,
            b = VK_COMPONENT_SWIZZLE_IDENTITY,
            a = VK_COMPONENT_SWIZZLE_IDENTITY
        )

        subresourceRange = VkImageSubresourceRange(
            aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
            baseMipLevel = 0, levelCount = 1,
            baseArrayLayer = 0, layerCount = 1
        )

        create_info = VkImageViewCreateInfo(
            image = image, viewType = VK_IMAGE_VIEW_TYPE_2D,
            format = format.format, components = components, subresourceRange = subresourceRange
        )


        labubu = SwapChainFrame()
        labubu.image = image
        labubu.image_view = vkCreateImageView(
            device = logicalDevice, pCreateInfo = create_info, pAllocator = None
        )

        bundle.frames.append(labubu)

    bundle.format = format.format
    bundle.extent = extent

    return bundle

def read_shader_src(filename):

    with open(filename, "rb") as file:

        code = file.read()

    return code

def create_shader_module(device, filename):

    code = read_shader_src(filename)

    createInfo = VkShaderModuleCreateInfo(
        codeSize = len(code),
        pCode = code
    )

    return vkCreateShaderModule(
        device = device, pCreateInfo = createInfo, pAllocator = None
    )

class InputBundle:
    def __init__(self, device, swapchainImageFormat, swapchainExtent, vertexFilePath, fragmentFilePath):
        self.device = device
        self.swapchainImageFormat = swapchainImageFormat
        self.swapchainExtent = swapchainExtent
        self.vertexFilePath = vertexFilePath
        self.fragmentFilePath = fragmentFilePath
    

class OutputBundle:
    def __init__(self, pipelineLayout, renderPass, pipeline):
        self.pipelineLayout = pipelineLayout
        self.renderPass = renderPass
        self.pipeline = pipeline

def create_render_pass(device, swapchainImageFormat):
    colorAttachment = VkAttachmentDescription(
        format = swapchainImageFormat,
        samples = VK_SAMPLE_COUNT_1_BIT,
        loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
        storeOp = VK_ATTACHMENT_STORE_OP_STORE,
        stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE,
        stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE,
        initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        finalLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR
    )

    colorAttachmentRef = VkAttachmentReference(
        attachment = 0,
        layout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL
    )

    subpass = VkSubpassDescription(
        pipelineBindPoint=VK_PIPELINE_BIND_POINT_GRAPHICS,
        colorAttachmentCount = 1,
        pColorAttachments = colorAttachmentRef
    )

    renderPassInfo = VkRenderPassCreateInfo(
        attachmentCount = 1,
        pAttachments = colorAttachment,
        subpassCount = 1,
        pSubpasses = subpass
    )


    return vkCreateRenderPass(device, renderPassInfo, None)

def create_descriptor_set_layout(device, binding, flags):

    camera_binding = VkDescriptorSetLayoutBinding(
        binding=binding,
        descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
        descriptorCount=1,
        stageFlags=flags
    )

    layout_info = VkDescriptorSetLayoutCreateInfo(
        bindingCount=binding+1,
        pBindings=[camera_binding]
    )

    return vkCreateDescriptorSetLayout(
        device,
        layout_info,
        None
    )

def create_descriptor_pool(device):

    pool_size = VkDescriptorPoolSize(
        type=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
        descriptorCount=1
    )

    pool_info = VkDescriptorPoolCreateInfo(
        poolSizeCount=1,
        pPoolSizes=[pool_size],
        maxSets=1
    )

    return vkCreateDescriptorPool(
        device,
        pool_info,
        None
    )

def allocate_descriptor_set(device, pool, layout):

    alloc_info = VkDescriptorSetAllocateInfo(
        descriptorPool=pool,
        descriptorSetCount=1,
        pSetLayouts=[layout]
    )

    return vkAllocateDescriptorSets(
        device,
        alloc_info
    )[0]

def update_descriptor_set(device, descriptor_set, camera_buffer, size):

    buffer_info = VkDescriptorBufferInfo(
        buffer=camera_buffer.buffer,
        offset=0,
        range=size
    )

    write = VkWriteDescriptorSet(
        dstSet=descriptor_set,
        dstBinding=0,
        descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
        descriptorCount=1,
        pBufferInfo=[buffer_info]
    )

    vkUpdateDescriptorSets(
        device,
        1,
        [write],
        0,
        None
    )

def create_pipeline_layout(device, all_layouts):

    pushConstantInfo = VkPushConstantRange(
        stageFlags = VK_SHADER_STAGE_VERTEX_BIT, offset = 0,
        size = 4 * 4 * 4
    )

    pipelineLayoutInfo = VkPipelineLayoutCreateInfo(
        sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        pushConstantRangeCount = 1, pPushConstantRanges = [pushConstantInfo],
        setLayoutCount = len(all_layouts), pSetLayouts = all_layouts
    )

    return vkCreatePipelineLayout(device, pipelineLayoutInfo, None)

def create_graphics_pipeline(inputBundle):
    bindingDescriptions = get_pos_color_binding_description()
    attributeDescriptions = get_pos_color_attribute_description()
    vertexInputInfo = VkPipelineVertexInputStateCreateInfo(
        vertexBindingDescriptionCount = len(bindingDescriptions), pVertexBindingDescriptions = bindingDescriptions,
        vertexAttributeDescriptionCount = len(attributeDescriptions), pVertexAttributeDescriptions = attributeDescriptions,
    )

    print(f"Loading vertex shader at \"{inputBundle.vertexFilePath}\"")
    vertexShaderModule = create_shader_module(inputBundle.device, inputBundle.vertexFilePath)
    vertexShaderStageInfo = VkPipelineShaderStageCreateInfo(
        stage = VK_SHADER_STAGE_VERTEX_BIT,
        module = vertexShaderModule,
        pName = "main"
    )

    inputAssembly = VkPipelineInputAssemblyStateCreateInfo(
        topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST
    )

    viewport = VkViewport(
        x = 0,
        y = 0,
        width = inputBundle.swapchainExtent.width,
        height = inputBundle.swapchainExtent.height,
        minDepth = 0.0,
        maxDepth = 1.0
    )
    scissor = VkRect2D(
        offset = [0, 0],
        extent = inputBundle.swapchainExtent
    )
    viewPortState = VkPipelineViewportStateCreateInfo(
        viewportCount = 1,
        pViewports = viewport,
        scissorCount = 1,
        pScissors = scissor
    )
    rasterizer = VkPipelineRasterizationStateCreateInfo(
        depthClampEnable = VK_FALSE,
        rasterizerDiscardEnable = VK_FALSE,
        polygonMode = VK_POLYGON_MODE_FILL,
        lineWidth = 1.0,
        cullMode = VK_CULL_MODE_BACK_BIT,
        frontFace = VK_FRONT_FACE_CLOCKWISE,
        depthBiasEnable = VK_FALSE
    )

    multisampling = VkPipelineMultisampleStateCreateInfo(
        sampleShadingEnable = VK_FALSE,
        rasterizationSamples = VK_SAMPLE_COUNT_1_BIT
    )

    print(f"Loading fragment shader at \"{inputBundle.fragmentFilePath}\"")
    fragmentShaderModule = create_shader_module(inputBundle.device, inputBundle.fragmentFilePath)
    fragmentShaderStageInfo = VkPipelineShaderStageCreateInfo(
        stage = VK_SHADER_STAGE_FRAGMENT_BIT,
        module = fragmentShaderModule,
        pName = "main"
    )

    shaderStages = [vertexShaderStageInfo, fragmentShaderStageInfo]

    colorBlendAttachment = VkPipelineColorBlendAttachmentState(
        colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT | VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT,
        blendEnable = VK_FALSE
    )
    colorBlending = VkPipelineColorBlendStateCreateInfo(
        logicOpEnable = VK_FALSE,
        attachmentCount = 1,
        pAttachments = colorBlendAttachment,
        blendConstants = [0.0, 0.0,0.0, 0.0]
    )

    pipelineLayout = create_pipeline_layout(
        inputBundle.device,
        descriptorsets
    )
    renderpass = create_render_pass(inputBundle.device, inputBundle.swapchainImageFormat)

    pipelineInfo = VkGraphicsPipelineCreateInfo(
        stageCount = len(shaderStages),
        pStages = shaderStages,
        pVertexInputState = vertexInputInfo,
        pInputAssemblyState = inputAssembly,
        pViewportState = viewPortState,
        pRasterizationState = rasterizer,
        pMultisampleState = multisampling,
        pColorBlendState = colorBlending,
        layout = pipelineLayout,
        renderPass = renderpass,
        subpass = 0
    )

    graphicsPipeline = vkCreateGraphicsPipelines(inputBundle.device, VK_NULL_HANDLE, 1, pipelineInfo, None)[0]

    vkDestroyShaderModule(inputBundle.device, vertexShaderModule, None)
    vkDestroyShaderModule(inputBundle.device, fragmentShaderModule, None)

    return OutputBundle(
        pipelineLayout = pipelineLayout,
        renderPass = renderpass,
        pipeline = graphicsPipeline
    )

def make_pipeline(device, swapchainFormat, swapchainExtent):
    inputBundle = InputBundle(
        device = device,
        swapchainImageFormat = swapchainFormat,
        swapchainExtent = swapchainExtent,
        vertexFilePath = "shaders/vert.spv",
        fragmentFilePath = "shaders/frag.spv"
    )

    outputBundle = create_graphics_pipeline(inputBundle)
    pipelineLayout = outputBundle.pipelineLayout
    renderpass = outputBundle.renderPass
    pipeline = outputBundle.pipeline

    return outputBundle, pipelineLayout, renderpass, pipeline

def make_framebuffers(inputChunk, frames):

    for i,frame in enumerate(frames):

        attachments = [frame.image_view,]

        framebufferInfo = VkFramebufferCreateInfo(
            renderPass = inputChunk.renderpass,
            attachmentCount = 1,
            pAttachments = attachments,
            width = inputChunk.swapchainExtent.width,
            height = inputChunk.swapchainExtent.height,
            layers=1
        )

        try:
            frame.framebuffer = vkCreateFramebuffer(
                inputChunk.device, framebufferInfo, None
            )

            print(f"Made framebuffer for frame {i}")
            
        except:

            print(f"Failed to make framebuffer for frame {i}")

def finalize_setup(device, renderpass, swapchainExtent, swapchainFrames, physicalDevice, surface, instance):
    framebufferInput = FramebufferInput()
    framebufferInput.device = device
    framebufferInput.renderpass = renderpass
    framebufferInput.swapchainExtent = swapchainExtent

    make_framebuffers(
        framebufferInput, swapchainFrames
    )

    CommandPoolInput = commandPoolInputChunk()
    CommandPoolInput.device = device
    CommandPoolInput.physicalDevice = physicalDevice
    CommandPoolInput.surface = surface
    CommandPoolInput.instance = instance

    commandPool = make_command_pool(CommandPoolInput)

    commandbufferInput = commandBufferInputChunk()
    commandbufferInput.device = device
    commandbufferInput.commandPool = commandPool
    commandbufferInput.frames = swapchainFrames

    mainCommandBuffer = make_command_buffers(commandbufferInput)

    for frame in swapchainFrames:
        frame.inFlight = make_fence(device)
        frame.imageAvailable = make_semaphore(device)
        frame.renderFinished = make_semaphore(device)

    inFlightFence = make_fence(device)
    imageAvailable = make_semaphore(device)
    renderFinished = make_semaphore(device)

    return commandPool, mainCommandBuffer, inFlightFence, imageAvailable, renderFinished



#commands
class commandPoolInputChunk:

    def __init__(self):
        self.device = None
        self.physicalDevice = None
        self.surface = None
        self.instance = None

class commandBufferInputChunk:

    def __init__(self):

        self.device = None
        self.commandPool = None
        self.frames = None


def make_command_pool(inputChunk):

    queueFamilyIndices = find_queue_families(inputChunk.physicalDevice, inputChunk.instance, inputChunk.surface)

    poolInfo = VkCommandPoolCreateInfo(
        flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
        queueFamilyIndex = queueFamilyIndices.graphicsFamily
    )

    try:
        commandPool = vkCreateCommandPool(
            inputChunk.device, poolInfo, None
        )
        print("Created command pool")
        return commandPool
    except:
        print("Failed to create command pool")
        return None

def make_command_buffers(inputChunk):

    allocInfo = VkCommandBufferAllocateInfo(
        commandPool = inputChunk.commandPool,
        level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        commandBufferCount = 1
    )

    #Make a command buffer for each frame
    for i,frame in enumerate(inputChunk.frames):

        try:
            frame.commandbuffer = vkAllocateCommandBuffers(inputChunk.device, allocInfo)[0]

            print(f"Allocated command buffer for frame {i}")
        except:
            print(f"Failed to allocate command buffer for frame {i}")
    
    try:
        commandbuffer = vkAllocateCommandBuffers(inputChunk.device, allocInfo)[0]

        print(f"Allocated main command buffer")
        
        return commandbuffer
    except:
        print(f"Failed to allocate main command buffer")
        
        return None


def make_semaphore(device):

    semaphoreInfo = VkSemaphoreCreateInfo()

    try:

        return vkCreateSemaphore(device, semaphoreInfo, None)
    
    except:

        print("Failed to create semaphore")
        
        return None

def make_fence(device):

    fenceInfo = VkFenceCreateInfo(
        flags = VK_FENCE_CREATE_SIGNALED_BIT
    )

    try:

        return vkCreateFence(device, fenceInfo, None)
    
    except:

        print("Failed to create fence")
        
        return None

def record_draw_commands(renderpass, swapchainFrames, swapchainExtent, pipeline, commandBuffer, imageIndex, scene):

    beginInfo = VkCommandBufferBeginInfo()

    try:
        vkBeginCommandBuffer(commandBuffer, beginInfo)
    except:
        print("Failed to begin recording command buffer")
    
    renderpassInfo = VkRenderPassBeginInfo(
        renderPass = renderpass,
        framebuffer = swapchainFrames[imageIndex].framebuffer,
        renderArea = [[0,0], swapchainExtent]
    )
    
    clearColor = VkClearValue([[1.0, 0.5, 0.25, 1.0]])
    renderpassInfo.clearValueCount = 1
    renderpassInfo.pClearValues = ffi.addressof(clearColor)
    
    vkCmdBeginRenderPass(commandBuffer, renderpassInfo, VK_SUBPASS_CONTENTS_INLINE)
    
    vkCmdBindPipeline(commandBuffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline)

    vkCmdBindDescriptorSets(
        commandBuffer,
        VK_PIPELINE_BIND_POINT_GRAPHICS,
        pipelineLayout,
        0,
        len(descriptorsets),
        descriptorsets,
        0,
        None
    )

    prepare_scene(triangle_mesh, commandBuffer)

    """
    for position in scene.triangle_positions:
        model_transform = pyrr.Matrix44.from_translation(position, dtype=np.float32)

        objData = ffi.cast("float *", ffi.from_buffer(model_transform))
    """

    """
    vert = np.array([
        [0, 0, 0, 1.0],
        [0, 0.5, 0, 1.0],
        [0.5, 0.5, 0, 1.0],
    ], dtype=np.float32)

    frag = np.array([
        [1, 0, 0, 1],
        [0, 1, 0, 1],
        [0, 0, 1, 1],
    ], dtype=np.float32)

    test_instance = pyrr.Matrix44.from_translation([0.0, 0.0, 0.0], dtype=np.float32)

    instances = np.array(test_instance, dtype=np.float32)

    thing = np.concatenate((vert, frag, instances))
    objData = ffi.cast("float *", ffi.from_buffer(thing))


    vkCmdPushConstants(
        commandBuffer = commandBuffer, layout = pipelineLayout,
        stageFlags = VK_SHADER_STAGE_VERTEX_BIT, offset = 0,
        size = thing.nbytes, pValues = objData
    )

    """

    vkCmdDraw(
        commandBuffer = commandBuffer, vertexCount = 3, 
        instanceCount = 1, firstVertex = 0, firstInstance = 0
    )
    
    vkCmdEndRenderPass(commandBuffer)
    
    try:
        vkEndCommandBuffer(commandBuffer)
    except:
        print("Failed to end recording command buffer")

def render(device, inFlightFence, swapchain, imageAvailable, renderFinished, swapchainFrames, graphicsQueue, presentQueue, maxFramesInFlight, frameNumber, scene):

    #grab instance procedures
    vkAcquireNextImageKHR = vkGetDeviceProcAddr(device, 'vkAcquireNextImageKHR')
    vkQueuePresentKHR = vkGetDeviceProcAddr(device, 'vkQueuePresentKHR')

    vkWaitForFences(
        device = device, fenceCount = 1, pFences = [swapchainFrames[frameNumber].inFlight,], 
        waitAll = VK_TRUE, timeout = 1000000000
    )
    vkResetFences(
        device = device, fenceCount = 1, pFences = [swapchainFrames[frameNumber].inFlight,]
    )

    imageIndex = vkAcquireNextImageKHR(
        device = device, swapchain = swapchain, timeout = 1000000000, 
        semaphore = swapchainFrames[frameNumber].imageAvailable, fence = VK_NULL_HANDLE
    )

    commandBuffer = swapchainFrames[imageIndex].commandbuffer
    vkResetCommandBuffer(commandBuffer = commandBuffer, flags = 0)
    record_draw_commands(renderpass, swapchainFrames, swapchainExtent, pipeline, commandBuffer, imageIndex, scene)

    submitInfo = VkSubmitInfo(
        waitSemaphoreCount = 1, pWaitSemaphores = [swapchainFrames[frameNumber].imageAvailable,], 
        pWaitDstStageMask=[VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,],
        commandBufferCount = 1, pCommandBuffers = [commandBuffer,], signalSemaphoreCount = 1,
        pSignalSemaphores = [swapchainFrames[frameNumber].renderFinished,]
    )

    try:
        vkQueueSubmit(
            queue = graphicsQueue, submitCount = 1, 
            pSubmits = submitInfo, fence = swapchainFrames[frameNumber].inFlight
        )
    except:
        print("Failed to submit draw commands")
    
    presentInfo = VkPresentInfoKHR(
        waitSemaphoreCount = 1, pWaitSemaphores = [renderFinished,],
        swapchainCount = 1, pSwapchains = [swapchain,],
        pImageIndices = [imageIndex,]
    )
    vkQueuePresentKHR(presentQueue, presentInfo)

    frameNumber += 1
    frameNumber %= maxFramesInFlight


#CLASS

class Scene:

    def __init__(self):

        self.triangle_positions = []


        x = -1.0
        while x < 1.0:
            y = -1.0
            while y < 1.0:
                self.triangle_positions.append(
                    np.array([x, y, 0], dtype=np.float32)
                )
                y += 0.2
            x += 0.2


def get_pos_color_binding_description():

    return (
        VkVertexInputBindingDescription(
        binding = 0, stride = 32, inputRate = VK_VERTEX_INPUT_RATE_VERTEX
        ),
        VkVertexInputBindingDescription(
        binding = 1, stride = 68, inputRate = VK_VERTEX_INPUT_RATE_INSTANCE
        )
    )

def get_pos_color_attribute_description():

    return (
        VkVertexInputAttributeDescription(
            binding = 0, location = 0,
            format = VK_FORMAT_R32G32B32_SFLOAT,
            offset = 0
        ),
        VkVertexInputAttributeDescription(
            binding = 0, location = 1,
            format = VK_FORMAT_R32G32B32_SFLOAT,
            offset = 12              #8bytes = 2 (32bit) numbers
        ),
        VkVertexInputAttributeDescription(
            binding = 0, location = 2,
            format = VK_FORMAT_R32G32_SFLOAT,
            offset = 24
        ),
        VkVertexInputAttributeDescription(
            binding = 1, location = 3,
            format = VK_FORMAT_R32G32B32A32_SFLOAT,
            offset = 0
        ),
        VkVertexInputAttributeDescription(
            binding = 1, location = 4,
            format = VK_FORMAT_R32G32B32A32_SFLOAT,
            offset = 16
        ),
        VkVertexInputAttributeDescription(
            binding = 1, location = 5,
            format = VK_FORMAT_R32G32B32A32_SFLOAT,
            offset = 32
        ),
        VkVertexInputAttributeDescription(
            binding = 1, location = 6,
            format = VK_FORMAT_R32G32B32A32_SFLOAT,
            offset = 48
        ),
        VkVertexInputAttributeDescription(
            binding = 1, location = 7,
            format = VK_FORMAT_R32_SINT,
            offset = 64
        ),
        #where mat4 in the shader is pyrr.Matrix44.from_translation()
    )

class BufferInput:
    def __init__(self):
        self.size = None
        self.usage = None
        self.logical_device = None
        self.physical_device = None

class Buffer:
    def __init__(self):

        self.buffer = None
        self.buffer_memory = None

def create_buffer(input_chunk: BufferInput) -> Buffer:
    """
        Create and return a vkBuffer
    """

    """
    typedef struct VkBufferCreateInfo {
        VkStructureType        sType;
        const void*            pNext;
        VkBufferCreateFlags    flags;
        VkDeviceSize           size;
        VkBufferUsageFlags     usage;
        VkSharingMode          sharingMode;
        uint32_t               queueFamilyIndexCount;
        const uint32_t*        pQueueFamilyIndices;
    } VkBufferCreateInfo;
    """

    bufferInfo = VkBufferCreateInfo(
        size = input_chunk.size,
        usage = input_chunk.usage,
        sharingMode = VK_SHARING_MODE_EXCLUSIVE
    )

    buffer = Buffer()
    buffer.buffer = vkCreateBuffer(
        device = input_chunk.logical_device, pCreateInfo = bufferInfo,
        pAllocator = None
    )

    allocate_buffer_memory(buffer, input_chunk)

    return buffer

def find_memory_type_index(
    physical_device, supported_memory_indices, requested_properties) -> int:

    """
    typedef struct VkPhysicalDeviceMemoryProperties {
        uint32_t        memoryTypeCount;
        VkMemoryType    memoryTypes[VK_MAX_MEMORY_TYPES];
        uint32_t        memoryHeapCount;
        VkMemoryHeap    memoryHeaps[VK_MAX_MEMORY_HEAPS];
    } VkPhysicalDeviceMemoryProperties;
    """
    memory_properties = vkGetPhysicalDeviceMemoryProperties(
        physicalDevice = physical_device
    )

    for i in range(memory_properties.memoryTypeCount):

        #bit i of supportedMemoryIndices is set if that memory type
        # is supported by the device
        supported = supported_memory_indices & (1 << i)

        #propertyFlags holds all the memory properties supported 
        # by this memory type
        sufficient = (memory_properties.memoryTypes[i].propertyFlags & requested_properties) == requested_properties

        if supported and sufficient:
            return i
    
    return 0

def allocate_buffer_memory(buffer: Buffer, input_chunk: BufferInput):

    """
    typedef struct VkMemoryRequirements {
        VkDeviceSize    size;
        VkDeviceSize    alignment;
        uint32_t        memoryTypeBits;
    } VkMemoryRequirements;
    """

    memory_requirements = vkGetBufferMemoryRequirements(
        device = input_chunk.logical_device, buffer = buffer.buffer
    )

    """
    typedef struct VkMemoryAllocateInfo {
        VkStructureType    sType;
        const void*        pNext;
        VkDeviceSize       allocationSize;
        uint32_t           memoryTypeIndex;
    } VkMemoryAllocateInfo;
    """
    allocInfo = VkMemoryAllocateInfo(
        allocationSize = memory_requirements.size,
        memoryTypeIndex = find_memory_type_index(
            input_chunk.physical_device, memory_requirements.memoryTypeBits, 
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
            )
    )

    buffer.buffer_memory = vkAllocateMemory(
        device = input_chunk.logical_device, pAllocateInfo = allocInfo, 
        pAllocator = None
    )

    vkBindBufferMemory(
        device = input_chunk.logical_device, buffer = buffer.buffer, 
        memory = buffer.buffer_memory, memoryOffset = 0
    )

class TriangleMesh:


    def __init__(self, logical_device, physical_device):

        self.logical_device = logical_device

        vertices = np.array(
            (0.0, -0.05, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0,
             0.05, 0.05, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0,
            -0.05, 0.05, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0,), dtype = np.float32
        )

        instance_dtype = np.dtype([
            ("model", np.float32, (4,4)),
            ("layer", np.int32)
        ])

        instances = np.zeros(1, dtype=instance_dtype)

        instances[0]["model"] = pyrr.Matrix44.from_translation(
            [0.0,0.0,0.0],
            dtype=np.float32
        )

        instances[0]["layer"] = 0

        input_chunk = BufferInput()
        input_chunk.logical_device = logical_device
        input_chunk.physical_device = physical_device
        input_chunk.size = vertices.nbytes
        input_chunk.usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT

        instbufferinput = BufferInput()
        instbufferinput.logical_device = logical_device
        instbufferinput.physical_device = physical_device
        instbufferinput.size = instances.nbytes
        instbufferinput.usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT

        self.vertex_buffer = create_buffer(input_chunk)
        self.instance_buffer = create_buffer(instbufferinput)

        memory_location = vkMapMemory(
            device = self.logical_device, memory = self.vertex_buffer.buffer_memory, 
            offset = 0, size = input_chunk.size, flags = 0
        )
        memory_location2 = vkMapMemory(
            device = self.logical_device, memory = self.instance_buffer.buffer_memory, 
            offset = 0, size = instbufferinput.size, flags = 0
        )
        # (location to move to, data to move, size in bytes)
        ffi.memmove(memory_location, vertices, input_chunk.size)
        ffi.memmove(memory_location2, instances, instbufferinput.size)
        vkUnmapMemory(device = self.logical_device, memory = self.vertex_buffer.buffer_memory)
        vkUnmapMemory(device = self.logical_device, memory = self.instance_buffer.buffer_memory)


    def destroy(self):

        vkDestroyBuffer(
            device = self.logical_device, buffer = self.vertex_buffer.buffer, 
            pAllocator = None
        )
        vkFreeMemory(
            device = self.logical_device, 
            memory = self.vertex_buffer.buffer_memory, pAllocator = None
        )
        vkDestroyBuffer(
            device = self.logical_device, buffer = self.instance_buffer.buffer, 
            pAllocator = None
        )
        vkFreeMemory(
            device = self.logical_device, 
            memory = self.instance_buffer.buffer_memory, pAllocator = None
        )

def make_assets(device, physicalDevice):
    triangle_mesh = TriangleMesh(device, physicalDevice)

    return triangle_mesh


def prepare_scene(triangle_mesh, commandBuffer):
    vkCmdBindVertexBuffers(
        commandBuffer = commandBuffer, firstBinding = 0, bindingCount = 2,
        pBuffers = (triangle_mesh.vertex_buffer.buffer, triangle_mesh.instance_buffer.buffer),
        pOffsets = (0, 0)
    )


#===============================
#             MAIN
#===============================


glfw.init()

glfw.window_hint(glfw.CLIENT_API, glfw.NO_API)

window = glfw.create_window(600, 480, "Vulkan Test", None, None)

instance = make_instance()

c_style_surface = ffi.new("VkSurfaceKHR*")
if glfw.create_window_surface(instance = instance, window = window, allocator = None, surface = c_style_surface) != VK_SUCCESS: print("Surface cretaion FAILED!!!!")
surface = c_style_surface[0]
(
    physicalDevice, device,
    graphicsQueue, presentQueue,
    swapchain, swapchainFrames,
    swapchainFormat, swapchainExtent,
    maxFramesInFlight, frameNumber
) = make_device(instance, surface, 600, 600)
properties = vkGetPhysicalDeviceProperties(physicalDevice)
print(f"Choosed physical device: {properties.deviceName}")

camera_dtype = np.dtype([
    ("projection", np.float32, (4, 4)),
    ("view", np.float32, (4, 4))
])

camera_data = np.zeros(1, dtype=camera_dtype)

camera_data["projection"][0] = np.array(pyrr.Matrix44.perspective_projection(60, 600/480, 0.1, 1000), dtype=np.float32)
camera_data["view"][0] = np.array(pyrr.Matrix44.look_at([0, 0, 0], [1, 0, 0], [0, 1, 0]), dtype=np.float32)


camera_input = BufferInput()
camera_input.logical_device = device
camera_input.physical_device = physicalDevice
camera_input.size = camera_data.nbytes
camera_input.usage = VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT

camera_buffer = create_buffer(camera_input)

memory = vkMapMemory(
    device=device,
    memory=camera_buffer.buffer_memory,
    offset=0,
    size=camera_data.nbytes,
    flags=0
)

ffi.memmove(memory, camera_data, camera_data.nbytes)

vkUnmapMemory(device, camera_buffer.buffer_memory)

descriptor_layout = create_descriptor_set_layout(device, 0, VK_SHADER_STAGE_VERTEX_BIT)

descriptor_pool = create_descriptor_pool(device)

descriptor_set = allocate_descriptor_set(
    device,
    descriptor_pool,
    descriptor_layout
)

update_descriptor_set(
    device,
    descriptor_set,
    camera_buffer,
    camera_data.nbytes
)

thing = BufferInput()
thing.logical_device = device
thing.physical_device = physicalDevice
thing.size = camera_data.nbytes
thing.usage = VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT

light_buffer = create_buffer(thing)

thing_dtype = np.dtype([
    ("lightPos", np.float32, (3)),
    ("viewPos", np.float32, (3))
])

light_data = np.zeros(1, dtype=thing_dtype)

light_data[0]["lightPos"] = [0.0, 0.0, 0.0]
light_data[0]["viewPos"] = [0.0, 0.0, 0.0]


light_layout = create_descriptor_set_layout(device, 0, VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT)

light_pool = create_descriptor_pool(device)

light_set = allocate_descriptor_set(
    device,
    light_pool,
    light_layout
)

update_descriptor_set(
    device,
    light_set,
    camera_buffer,
    camera_data.nbytes
)

all_layouts = [descriptor_layout, light_layout]

descriptorsets = [descriptor_set, light_set]

outputBundle, pipelineLayout, renderpass, pipeline = make_pipeline(device, swapchainFormat, swapchainExtent)

(
    commandPool,
    mainCommandBuffer,
    inFlightFence,
    imageAvailable,
    renderFinished,
) = finalize_setup(device, renderpass, swapchainExtent, swapchainFrames, physicalDevice, surface, instance)



outputBundle, pipelineLayout, renderpass, pipeline = make_pipeline(device, swapchainFormat, swapchainExtent)

(
    commandPool,
    mainCommandBuffer,
    inFlightFence,
    imageAvailable,
    renderFinished,
) = finalize_setup(device, renderpass, swapchainExtent, swapchainFrames, physicalDevice, surface, instance)


triangle_mesh = make_assets(device, physicalDevice)

frameNumber = 0


scene = Scene()

last = time.time()
frames_passed = 0

while True:
    glfw.poll_events()

    if glfw.window_should_close(window):
        break

    render(device, inFlightFence, swapchain, imageAvailable, renderFinished, swapchainFrames, graphicsQueue, presentQueue, maxFramesInFlight, frameNumber, scene)

    now = time.time()
    if now - last >= 1:
        last = now
        glfw.set_window_title(window, f"Vulkan Test | FPS: {frames_passed}")

        frames_passed = 0
    
    frames_passed += 1

triangle_mesh.destroy()

for frame in swapchainFrames:

    vkDestroyFence(device, frame.inFlight, None)
    vkDestroySemaphore(device, frame.imageAvailable, None)
    vkDestroySemaphore(device, frame.renderFinished, None)

    vkDestroyImageView(
        device = device, imageView = frame.image_view, pAllocator = None
    )
    vkDestroyFramebuffer(
        device = device, framebuffer = frame.framebuffer, pAllocator = None
    )


vkDestroyCommandPool(device, commandPool, None)

vkDestroyPipeline(device, pipeline, None)
vkDestroyPipelineLayout(device, pipelineLayout, None)
vkDestroyRenderPass(device, renderpass, None)

vkGetDeviceProcAddr(device, 'vkDestroySwapchainKHR')(device, swapchain, None)

vkDestroyDevice(device = device, pAllocator = None)

vkGetInstanceProcAddr(instance, 'vkDestroySurfaceKHR')(instance, surface, None)

vkDestroyInstance(instance, None)

glfw.terminate()