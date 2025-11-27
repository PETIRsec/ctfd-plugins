# Docker Setup for Face & Location Verification Plugin

## Installation

This plugin requires the `cryptography` library for end-to-end encryption. 

### Option 1: Add to CTFd requirements.txt

Add this line to your main `CTFd/requirements.txt`:

```
cryptography>=41.0.0
```

### Option 2: Install in Docker container

If you're using Docker, you can install it by:

1. **Modify your Dockerfile** to install the dependency:
   ```dockerfile
   RUN pip install cryptography>=41.0.0
   ```

2. **Or install at runtime** (if you have access to the container):
   ```bash
   docker exec -it <container_name> pip install cryptography>=41.0.0
   ```

3. **Or use a requirements file** in your Docker setup:
   ```dockerfile
   COPY plugins/face_location_verification/requirements.txt /tmp/plugin-requirements.txt
   RUN pip install -r /tmp/plugin-requirements.txt
   ```

## Rebuild Docker Container

After adding the dependency, rebuild your Docker container:

```bash
docker-compose build
# or
docker build -t ctfd .
```

## Verify Installation

After restarting CTFd, check that cryptography is available:

```bash
docker exec -it <container_name> python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; print('Cryptography installed successfully')"
```

## Notes

- The plugin will work without cryptography, but encryption will be disabled (fallback mode)
- For production use, cryptography is **strongly recommended** for end-to-end encryption
- The plugin includes obfuscated JavaScript to prevent deobfuscation of encryption logic

