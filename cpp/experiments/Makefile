CXX ?= g++
CXXFLAGS ?= -O3 -DNDEBUG -std=c++17 -Wall -Wextra -Wpedantic
HEADERS := $(wildcard ../include/ima/*.hpp) $(wildcard *.hpp)
BUILD := build
.PHONY: all sanitize test
all: $(BUILD)/experiment $(BUILD)/experiment_memory
$(BUILD):
	mkdir -p $@
$(BUILD)/experiment: bench.cpp $(HEADERS) Makefile | $(BUILD)
	$(CXX) -I../include $(CXXFLAGS) '-DIMA_EXPERIMENT_FLAGS="$(CXXFLAGS)"' $< -o $@
$(BUILD)/experiment_memory: bench.cpp $(HEADERS) Makefile | $(BUILD)
	$(CXX) -I../include $(CXXFLAGS) -DIMA_TRACK_ALLOC '-DIMA_EXPERIMENT_FLAGS="$(CXXFLAGS) -DIMA_TRACK_ALLOC"' $< -o $@
sanitize: | $(BUILD)
	$(CXX) -I../include -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer -DIMA_TRACK_ALLOC bench.cpp -o $(BUILD)/experiment_sanitize
